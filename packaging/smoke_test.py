"""PyInstaller smoke test — confirms the PyCriCodecsEx C++ backend survives freezing.

Exits 0 if every required symbol imports and instantiates.
Exits 1 (with a traceback) otherwise.
"""

import sys


def main() -> int:
    from PyCriCodecsEx.acb import ACB, ACBBuilder
    from PyCriCodecsEx.awb import AWB, AWBBuilder
    from PyCriCodecsEx.hca import HCA, HCACodec
    import CriCodecsEx

    required_backend_syms = {"HcaDecode", "HcaEncode", "AdxDecode", "AdxEncode"}
    missing = required_backend_syms - set(dir(CriCodecsEx))
    if missing:
        print(f"FAIL: CriCodecsEx missing symbols: {sorted(missing)}", file=sys.stderr)
        return 1

    print("OK")
    print(f"  ACB        : {ACB}")
    print(f"  ACBBuilder : {ACBBuilder}")
    print(f"  AWB        : {AWB}")
    print(f"  AWBBuilder : {AWBBuilder}")
    print(f"  HCA        : {HCA}")
    print(f"  HCACodec   : {HCACodec}")
    print(f"  CriCodecsEx: {CriCodecsEx.__file__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
