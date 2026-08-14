from __future__ import annotations

import argparse
from collections.abc import Sequence

from elanquant.cli.doctor import add_doctor_arguments, run_doctor_command
from elanquant.cli.smoke import add_smoke_arguments, run_smoke_command
from elanquant.repro.bootstrap import add_bootstrap_parser
from elanquant.repro.data import add_data_parser
from elanquant.repro.weights import add_weights_parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elanquant")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_bootstrap_parser(subparsers)
    add_data_parser(subparsers)
    add_weights_parser(subparsers)
    doctor = subparsers.add_parser("doctor", help="Check a runtime profile without writing")
    add_doctor_arguments(doctor)
    doctor.set_defaults(handler=run_doctor_command)
    smoke = subparsers.add_parser("smoke", help="Run a synthetic execution smoke test")
    add_smoke_arguments(smoke)
    smoke.set_defaults(handler=run_smoke_command)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
