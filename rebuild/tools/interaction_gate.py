"""Exercise firmware input, JSON replies and socket deadlines as native code."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    cjson=Path(os.environ["IDF_PATH"])/"components"/"json"/"cJSON"
    if not (cjson/"cJSON.c").is_file():
        raise RuntimeError("Activate the matching ESP-IDF before running this gate")
    flags=["-O2","-fsanitize=address,undefined"]
    with tempfile.TemporaryDirectory(prefix="kadence-interaction-") as directory:
        work=Path(directory)
        obj=work/"cjson.o"
        subprocess.run(["cc",*flags,"-I",str(cjson),"-c",str(cjson/"cJSON.c"),"-o",str(obj)],check=True)
        for name in ("input_feedback","voice_socket","control_frame"):
            output=work/name
            sources=[str(ROOT/"tests"/(name+"_test.cpp"))]
            if name=="control_frame": sources.append(str(obj))
            subprocess.run(["g++","-std=c++17","-Wall","-Wextra","-Werror",*flags,
                            "-pthread","-I",str(cjson),*sources,"-o",str(output)],check=True)
            subprocess.run([str(output)],check=True)


if __name__=="__main__": main()
