def fix():
    with open("index.html", "r") as f:
        lines = f.readlines()

    out = []
    skip = False
    for i, line in enumerate(lines):
        if "const logout = () => {" in line and i > 6300:
            skip = True

        if skip and "};" in line:
            skip = False
            continue

        if not skip:
            out.append(line)

    with open("index.html", "w") as f:
        f.writelines(out)

if __name__ == "__main__":
    fix()
