import argparse


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify_thresh_single", type=float, default=0.94)
    parser.add_argument("--verify_thresh_multi", type=float, default=0.9)
    parser.add_argument(
        "--verify_strategy",
        choices=["fixed-num", "single-token", "multiple-tokens", "hybrid"],
        default="fixed-num",
    )
    return parser.parse_args()


def args_proc(args):
    if args.algorithm == 'pipesd':
        args.verify_strategy = 'hybrid'
    return args
