import os
from itertools import combinations

import cv2
import numpy as np

from src.constants.image_processing import (
    DEFAULT_BLACK_COLOR,
    DEFAULT_BORDER_REMOVE,
    DEFAULT_GAUSSIAN_BLUR_PARAMS_MARKER,
    DEFAULT_LINE_WIDTH,
    DEFAULT_NORMALIZE_PARAMS,
    DEFAULT_WHITE_COLOR,
    ERODE_RECT_COLOR,
    EROSION_PARAMS,
    MARKER_RECTANGLE_COLOR,
    NORMAL_RECT_COLOR,
    QUADRANT_DIVISION,
)
from src.logger import logger
from src.processors.interfaces.ImagePreprocessor import ImagePreprocessor
from src.utils.image import ImageUtils
from src.utils.interaction import InteractionUtils


class CropOnMarkers(ImagePreprocessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config = self.tuning_config
        marker_ops = self.options
        self.threshold_circles = []
        # img_utils = ImageUtils()

        # options with defaults
        self.marker_path = os.path.join(
            self.relative_dir, marker_ops.get("relativePath", "omr_marker.jpg")
        )
        self.min_matching_threshold = marker_ops.get("min_matching_threshold", 0.3)
        self.max_matching_variation = marker_ops.get("max_matching_variation", 0.41)
        self.marker_rescale_range = tuple(
            int(r) for r in marker_ops.get("marker_rescale_range", (35, 100))
        )
        self.marker_rescale_steps = int(marker_ops.get("marker_rescale_steps", 10))
        self.apply_erode_subtract = marker_ops.get("apply_erode_subtract", True)
        self.search_mode = str(
            marker_ops.get(
                "searchMode",
                "global" if marker_ops.get("globalSearch") else "quadrants",
            )
        ).lower()
        self.marker = self.load_marker(marker_ops, config)

    def __str__(self):
        return self.marker_path

    def exclude_files(self):
        return [self.marker_path]

    def _get_centres_global(self, image_eroded_sub, optimal_marker, file_path):
        config = self.tuning_config
        _h, w = optimal_marker.shape[:2]
        res = cv2.matchTemplate(image_eroded_sub, optimal_marker, cv2.TM_CCOEFF_NORMED)

        res_work = res.copy()
        candidates = []
        suppress_x = max(1, int(w * 0.9))
        suppress_y = max(1, int(_h * 0.9))
        max_candidates = 20
        for _ in range(max_candidates):
            _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(res_work)
            if max_val < self.min_matching_threshold:
                break
            x, y = int(max_loc[0]), int(max_loc[1])
            candidates.append((float(max_val), x, y))
            x0 = max(0, x - suppress_x)
            y0 = max(0, y - suppress_y)
            x1 = min(res_work.shape[1] - 1, x + suppress_x)
            y1 = min(res_work.shape[0] - 1, y + suppress_y)
            res_work[y0 : y1 + 1, x0 : x1 + 1] = 0

        if len(candidates) < 4:
            logger.error(file_path, "\nError: Not enough markers found in global search.")
            if config.outputs.show_image_level >= 1:
                InteractionUtils.show(f"Marker search: {file_path}", image_eroded_sub, 0, config=config)
                InteractionUtils.show("matchTemplate res", res, 1, config=config)
            return None, None, None

        top_k = candidates[: min(len(candidates), 12)]
        best = None
        best_area = None
        best_score = None
        for combo in combinations(top_k, 4):
            centres = np.array(
                [[x + w / 2, y + _h / 2] for (_t, x, y) in combo], dtype="float32"
            )
            area = float(
                (centres[:, 0].max() - centres[:, 0].min())
                * (centres[:, 1].max() - centres[:, 1].min())
            )
            score = float(sum(t for (t, _x, _y) in combo))
            if best_area is None or area > best_area or (area == best_area and score > best_score):
                best = combo
                best_area = area
                best_score = score

        if best is None:
            return None, None, None

        centres = [[x + w / 2, y + _h / 2] for (_t, x, y) in best]
        avg_t = float(sum(t for (t, _x, _y) in best) / 4)
        rects = [(x, y, w, _h) for (_t, x, y) in best]
        return centres, rects, avg_t

    def apply_filter(self, image, file_path):
        config = self.tuning_config
        image_instance_ops = self.image_instance_ops
        image_eroded_sub = ImageUtils.normalize_util(
            image
            if self.apply_erode_subtract
            else (
                image
                - cv2.erode(
                    image,
                    kernel=np.ones(EROSION_PARAMS["kernel_size"]),
                    iterations=EROSION_PARAMS["iterations"],
                )
            )
        )
        quads = {}
        origins = [[0, 0], [0, 0], [0, 0], [0, 0]]
        if self.search_mode not in {"global", "full", "all"}:
            # Quads on warped image
            h1, w1 = image_eroded_sub.shape[:2]
            midh, midw = (
                h1 // QUADRANT_DIVISION["height_factor"],
                w1 // QUADRANT_DIVISION["width_factor"],
            )
            origins = [[0, 0], [midw, 0], [0, midh], [midw, midh]]
            quads[0] = image_eroded_sub[0:midh, 0:midw]
            quads[1] = image_eroded_sub[0:midh, midw:w1]
            quads[2] = image_eroded_sub[midh:h1, 0:midw]
            quads[3] = image_eroded_sub[midh:h1, midw:w1]

            # Draw Quadlines (quadrant mode debugging)
            image_eroded_sub[:, midw : midw + 2] = DEFAULT_WHITE_COLOR
            image_eroded_sub[midh : midh + 2, :] = DEFAULT_WHITE_COLOR

        best_scale, all_max_t = self.getBestMatch(image_eroded_sub)
        if best_scale is None:
            if config.outputs.show_image_level >= 1:
                InteractionUtils.show("Quads", image_eroded_sub, config=config)
            return None

        optimal_marker = ImageUtils.resize_util_h(
            self.marker, u_height=int(self.marker.shape[0] * best_scale)
        )
        _h, w = optimal_marker.shape[:2]
        centres = []
        rects = []
        avg_t = 0.0

        if self.search_mode in {"global", "full", "all"}:
            centres, rects, avg_t = self._get_centres_global(
                image_eroded_sub, optimal_marker, file_path
            )
            if centres is None:
                return None
        else:
            sum_t, max_t = 0, 0
            quarter_match_log = "Matching Marker:  "
            for k in range(0, 4):
                res = cv2.matchTemplate(quads[k], optimal_marker, cv2.TM_CCOEFF_NORMED)
                max_t = res.max()
                quarter_match_log += f"Quarter{str(k + 1)}: {str(round(max_t, 3))}\t"
                if (
                    max_t < self.min_matching_threshold
                    or abs(all_max_t - max_t) >= self.max_matching_variation
                ):
                    if self.search_mode in {"auto", "fallback"}:
                        centres, rects, avg_t = self._get_centres_global(
                            image_eroded_sub, optimal_marker, file_path
                        )
                        if centres is None:
                            return None
                        break

                    logger.error(
                        file_path,
                        "\nError: No circle found in Quad",
                        k + 1,
                        "\n\t min_matching_threshold",
                        self.min_matching_threshold,
                        "\t max_matching_variation",
                        self.max_matching_variation,
                        "\t max_t",
                        max_t,
                        "\t all_max_t",
                        all_max_t,
                    )
                    if config.outputs.show_image_level >= 1:
                        InteractionUtils.show(
                            f"No markers: {file_path}",
                            image_eroded_sub,
                            0,
                            config=config,
                        )
                        InteractionUtils.show(
                            f"res_Q{str(k + 1)} ({str(max_t)})",
                            res,
                            1,
                            config=config,
                        )
                    return None

                pt = np.argwhere(res == max_t)[0]
                pt = [pt[1], pt[0]]
                pt[0] += origins[k][0]
                pt[1] += origins[k][1]
                rects.append((pt[0], pt[1], w, _h))
                centres.append([pt[0] + w / 2, pt[1] + _h / 2])
                sum_t += max_t

            if centres and isinstance(centres[0], list):
                logger.info(quarter_match_log)
                logger.info(f"Optimal Scale: {best_scale}")
                avg_t = float(sum_t / 4) if sum_t else 0.0

        # analysis data
        if avg_t:
            self.threshold_circles.append(avg_t)

        for (x, y, rw, rh) in rects:
            pt = (int(x), int(y))
            image = cv2.rectangle(
                image,
                pt,
                (int(x + rw), int(y + rh)),
                MARKER_RECTANGLE_COLOR,
                DEFAULT_LINE_WIDTH,
            )
            image_eroded_sub = cv2.rectangle(
                image_eroded_sub,
                pt,
                (int(x + rw), int(y + rh)),
                ERODE_RECT_COLOR if self.apply_erode_subtract else NORMAL_RECT_COLOR,
                4,
            )

        image = ImageUtils.four_point_transform(image, np.array(centres))
        # appendSaveImg(1,image_eroded_sub)
        # appendSaveImg(1,image_norm)

        image_instance_ops.append_save_img(2, image_eroded_sub)
        # Debugging image -
        # res = cv2.matchTemplate(image_eroded_sub,optimal_marker,cv2.TM_CCOEFF_NORMED)
        # res[ : , midw:midw+2] = 255
        # res[ midh:midh+2, : ] = 255
        # show("Markers Matching",res)
        if config.outputs.show_image_level >= 2 and config.outputs.show_image_level < 4:
            image_eroded_sub = ImageUtils.resize_util_h(
                image_eroded_sub, image.shape[0]
            )
            image_eroded_sub[:, -DEFAULT_BORDER_REMOVE:] = DEFAULT_BLACK_COLOR
            h_stack = np.hstack((image_eroded_sub, image))
            InteractionUtils.show(
                f"Warped: {file_path}",
                ImageUtils.resize_util(
                    h_stack, int(config.dimensions.display_width * 1.6)
                ),
                0,
                0,
                [0, 0],
                config=config,
            )
        # iterations : Tuned to 2.
        # image_eroded_sub = image_norm - cv2.erode(image_norm, kernel=np.ones((5,5)),iterations=2)
        return image

    def load_marker(self, marker_ops, config):
        if not os.path.exists(self.marker_path):
            logger.error(
                "Marker not found at path provided in template:",
                self.marker_path,
            )
            exit(31)

        marker = cv2.imread(self.marker_path, cv2.IMREAD_GRAYSCALE)

        if "sheetToMarkerWidthRatio" in marker_ops:
            marker = ImageUtils.resize_util(
                marker,
                config.dimensions.processing_width
                / int(marker_ops["sheetToMarkerWidthRatio"]),
            )
        marker = cv2.GaussianBlur(
            marker,
            DEFAULT_GAUSSIAN_BLUR_PARAMS_MARKER["kernel_size"],
            DEFAULT_GAUSSIAN_BLUR_PARAMS_MARKER["sigma_x"],
        )
        marker = cv2.normalize(
            marker,
            None,
            alpha=DEFAULT_NORMALIZE_PARAMS["alpha"],
            beta=DEFAULT_NORMALIZE_PARAMS["beta"],
            norm_type=cv2.NORM_MINMAX,
        )

        if self.apply_erode_subtract:
            marker -= cv2.erode(
                marker,
                kernel=np.ones(EROSION_PARAMS["kernel_size"]),
                iterations=EROSION_PARAMS["iterations"],
            )

        return marker

    # Resizing the marker within scaleRange at rate of descent_per_step to
    # find the best match.
    def getBestMatch(self, image_eroded_sub):
        config = self.tuning_config
        descent_per_step = (
            self.marker_rescale_range[1] - self.marker_rescale_range[0]
        ) // self.marker_rescale_steps
        _h, _w = self.marker.shape[:2]
        res, best_scale = None, None
        all_max_t = 0

        for r0 in np.arange(
            self.marker_rescale_range[1],
            self.marker_rescale_range[0],
            -1 * descent_per_step,
        ):  # reverse order
            s = float(r0 * 1 / 100)
            if s == 0.0:
                continue
            rescaled_marker = ImageUtils.resize_util_h(
                self.marker, u_height=int(_h * s)
            )
            # res is the black image with white dots
            res = cv2.matchTemplate(
                image_eroded_sub, rescaled_marker, cv2.TM_CCOEFF_NORMED
            )

            max_t = res.max()
            if all_max_t < max_t:
                # print('Scale: '+str(s)+', Circle Match: '+str(round(max_t*100,2))+'%')
                best_scale, all_max_t = s, max_t

        if all_max_t < self.min_matching_threshold:
            logger.warning(
                "\tTemplate matching too low! Consider rechecking preProcessors applied before this."
            )
            if config.outputs.show_image_level >= 1:
                InteractionUtils.show("res", res, 1, 0, config=config)

        if best_scale is None:
            logger.warning(
                "No matchings for given scaleRange:", self.marker_rescale_range
            )
        return best_scale, all_max_t
