"""Task 21 Step 7: do two VCDs hold the same value changes?

    uv run docs/reports/2026-11-pilot/viewers/vcd_equal.py A.vcd B.vcd

A is fst2vcd's output for the FST export, B the VCD export. Identifier codes, header text, where
a range is written (`rgb6[5:0]` or `rgb6 [5:0]`) and the order of changes within one timestamp may
differ; each file is read as the set of
(time, scope.signal, value) changes, with vector values compared as integers (fst2vcd may drop
leading zeros). Prints the counts and the first differences; exits 1 if they differ.
"""
import sys


def changes(path: str) -> tuple[set, int]:
    names, scope, out, t, n = {}, [], set(), 0, 0
    with open(path, encoding="ascii") as f:
        for line in f:
            w = line.split()
            if not w:
                continue
            if w[0] == "$scope":
                scope.append(w[2])
            elif w[0] == "$upscope":
                scope.pop()
            elif w[0] == "$var":
                names[w[3]] = ".".join(scope + [w[4].split("[")[0]])   # "rgb6[5:0]" or "rgb6 [5:0]"
            elif w[0][0] == "#":
                t = int(w[0][1:])
            elif w[0][0] in "bB":
                out.add((t, names[w[1]], int(w[0][1:], 2)))
                n += 1
            elif w[0][0] in "01" and len(w) == 1 and w[0][1:] in names:
                out.add((t, names[w[0][1:]], int(w[0][0])))
                n += 1
    return out, n


def main() -> int:
    a, na = changes(sys.argv[1])
    b, nb = changes(sys.argv[2])
    print(f"A: {na:,} value changes, B: {nb:,}; equal: {'yes' if a == b and na == nb else 'no'}")
    for x in sorted(a - b)[:5]:
        print(f"only in A: {x}")
    for x in sorted(b - a)[:5]:
        print(f"only in B: {x}")
    return 0 if a == b and na == nb else 1


if __name__ == "__main__":
    sys.exit(main())
