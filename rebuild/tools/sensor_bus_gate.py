"""Run the production sensor state machine and wire serializer as native code."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    cjson = Path(os.environ["IDF_PATH"]) / "components/json/cJSON"
    flags = ["-O2", "-fsanitize=address,undefined"]
    with tempfile.TemporaryDirectory(prefix="kadence-sensors-") as directory:
        work = Path(directory)
        obj = work / "cjson.o"
        subprocess.run(["cc", *flags, "-I", str(cjson), "-c", str(cjson / "cJSON.c"), "-o", str(obj)], check=True)
        for name in ("sensor_bus", "sensor_protocol"):
            output = work / name
            sources = [str(ROOT / "tests" / (name + "_test.cpp"))]
            if name == "sensor_protocol": sources.append(str(obj))
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *flags,
                            "-I", str(cjson), *sources, "-o", str(output)], check=True)
            subprocess.run([str(output)], check=True)


if __name__ == "__main__":
    main()
