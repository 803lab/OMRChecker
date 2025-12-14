"""

 OMRChecker

 Author: Udayraj Deshmukh
 Github: https://github.com/Udayraj123

"""

import argparse
import sys
from pathlib import Path

from src.entry import entry_point
from src.logger import logger


def parse_args():
    # construct the argument parse and parse the arguments
    argparser = argparse.ArgumentParser()

    argparser.add_argument(
        "--gui",
        required=False,
        dest="gui",
        action="store_true",
        help="Launch the desktop GUI.",
    )

    argparser.add_argument(
        "--cli",
        required=False,
        dest="cli",
        action="store_true",
        help="Run the command-line interface.",
    )

    argparser.add_argument(
        "-i",
        "--inputDir",
        default=["inputs"],
        # https://docs.python.org/3/library/argparse.html#nargs
        nargs="*",
        required=False,
        type=str,
        dest="input_paths",
        help="Specify an input directory.",
    )

    argparser.add_argument(
        "-d",
        "--debug",
        required=False,
        dest="debug",
        action="store_false",
        help="Enables debugging mode for showing detailed errors",
    )

    argparser.add_argument(
        "-o",
        "--outputDir",
        default="outputs",
        required=False,
        dest="output_dir",
        help="Specify an output directory.",
    )

    argparser.add_argument(
        "-a",
        "--autoAlign",
        required=False,
        dest="autoAlign",
        action="store_true",
        help="(experimental) Enables automatic template alignment - \
        use if the scans show slight misalignments.",
    )

    argparser.add_argument(
        "-l",
        "--setLayout",
        required=False,
        dest="setLayout",
        action="store_true",
        help="Set up OMR template layout - modify your json file and \
        run again until the template is set.",
    )

    (
        args,
        unknown,
    ) = argparser.parse_known_args()

    args = vars(args)

    if len(unknown) > 0:
        logger.warning(f"\nError: Unknown arguments: {unknown}", unknown)
        argparser.print_help()
        exit(11)
    return args


def entry_point_for_args(args):
    if args["debug"] is True:
        # Disable tracebacks
        sys.tracebacklimit = 0
    for root in args["input_paths"]:
        entry_point(
            Path(root),
            args,
        )


def launch_gui() -> None:
    try:
        from omr_gui.app import main as gui_main
    except Exception as exc:  # pragma: no cover - depends on GUI deps/runtime
        logger.error("Failed to launch GUI:", exc)
        logger.error(
            "Tip: install GUI dependencies (e.g. `pip install -r requirements.txt`) and run from the repo root."
        )
        raise SystemExit(1) from exc

    gui_main()


if __name__ == "__main__":
    if "--gui" in sys.argv or (len(sys.argv) == 1 and "--cli" not in sys.argv):
        launch_gui()
    else:
        args = parse_args()
        if args.get("gui"):
            launch_gui()
        else:
            entry_point_for_args(args)
