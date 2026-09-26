"""Build and execute the readable percent-format source as a Jupyter notebook."""
from pathlib import Path
import re
import sys
import time

import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter
from jupyter_client.kernelspec import KernelSpecManager
from tempfile import TemporaryDirectory


def main():
    root = Path(__file__).resolve().parents[2]
    source = Path(__file__).with_name("macroplastic_eda.py")
    output = root / "notebooks" / "01_macroplastic_eda.ipynb"
    output.parent.mkdir(exist_ok=True)
    parts = re.split(r"^# %%([^\n]*)\n", source.read_text(), flags=re.MULTILINE)
    cells = []
    for marker, body in zip(parts[1::2], parts[2::2]):
        if "[markdown]" in marker:
            text = "\n".join(re.sub(r"^# ?", "", line) for line in body.strip().splitlines())
            cells.append(nbformat.v4.new_markdown_cell(text))
        else:
            cells.append(nbformat.v4.new_code_cell(body.strip()))
    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata.kernelspec = dict(name="python3", display_name="Python 3", language="python")
    started = time.monotonic()
    # Isolated kernelspec ensures exactly the runner's Python, without global installation.
    with TemporaryDirectory(prefix="littora-eda-kernel-") as temp:
        kernel_dir = Path(temp) / "python3"
        kernel_dir.mkdir()
        import json
        (kernel_dir / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "Python 3", "language": "python",
        }))
        manager = KernelSpecManager(kernel_dirs=[temp])
        from jupyter_client import KernelManager
        km = KernelManager(kernel_name="python3", kernel_spec_manager=manager)
        client = NotebookClient(notebook, km=km, timeout=600, resources={"metadata": {"path": str(root)}})
        try:
            client.execute(cleanup_kc=True)
        finally:
            nbformat.write(notebook, output)
    errors = [o for c in notebook.cells if c.cell_type == "code" for o in c.outputs if o.output_type == "error"]
    assert not errors, errors
    html, _ = HTMLExporter(template_name="lab").from_notebook_node(notebook)
    html_path = root / "reports" / "eda" / "macroplastic_eda.html"
    html_path.write_text(html)
    print(f"Executed {sum(c.cell_type == 'code' for c in cells)} code cells in {time.monotonic() - started:.1f}s")
    print(output.relative_to(root))
    print(html_path.relative_to(root))


if __name__ == "__main__":
    main()
