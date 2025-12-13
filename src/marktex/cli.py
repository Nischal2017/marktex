#!/usr/bin/env python3
"""Command-line interface for MarkTeX."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Literal


def check_dependencies() -> tuple[bool, list[str]]:
    """Check if required external dependencies are installed.

    Returns:
        Tuple of (all_found, missing_dependencies)
    """
    missing = []

    # Check for pandoc
    if subprocess.run(["which", "pandoc"], capture_output=True).returncode != 0:
        missing.append("pandoc")

    # Check for pandoc-mermaid filter
    if subprocess.run(["which", "pandoc-mermaid"], capture_output=True).returncode != 0:
        missing.append("pandoc-mermaid (install via: uv tool install --from pandoc-mermaid-filter pandoc-mermaid-filter)")

    # Check for latexmk
    if subprocess.run(["which", "latexmk"], capture_output=True).returncode != 0:
        missing.append("latexmk (install via: sudo apt-get install texlive-full)")

    # Check for mmdc (mermaid-cli)
    if subprocess.run(["which", "mmdc"], capture_output=True).returncode != 0:
        missing.append("mmdc (install via: npm install -g @mermaid-js/mermaid-cli)")

    return len(missing) == 0, missing


def determine_source_type(file_path: Path) -> str:
    """Determine source file type.

    Phase 1: Only supports 'markdown'
    Phase 2: Will support 'latex' for direct .tex editing

    Args:
        file_path: Path to the source file

    Returns:
        Source type ('markdown' or 'latex')

    Raises:
        NotImplementedError: If .tex file provided (Phase 2 feature)
        ValueError: If unsupported file type
    """
    if file_path.suffix == '.md':
        return 'markdown'
    elif file_path.suffix == '.tex':
        raise NotImplementedError(
            "Direct .tex editing not yet supported. "
            "This feature is planned for a future release."
        )
    else:
        raise ValueError(f"Unsupported file type: {file_path.suffix}")


def find_repo_root(start_path: Path) -> Optional[Path]:
    """Find the repository root by looking for PDF/, TEX/, or .git folders.

    Args:
        start_path: Path to start searching from

    Returns:
        Repository root path if found, None otherwise
    """
    current = start_path.resolve()

    # Walk up the directory tree
    while current != current.parent:
        # Check for markers of repo root
        if (current / "PDF").exists() or (current / "TEX").exists() or (current / ".git").exists():
            return current
        current = current.parent

    return None


def get_relative_path_from_root(file_path: Path, repo_root: Path) -> Path:
    """Get the relative path of a file from the repo root, excluding PDF/TEX/recent folders.

    Args:
        file_path: Absolute path to the file
        repo_root: Repository root path

    Returns:
        Relative path from repo root, excluding special folders
    """
    try:
        rel_path = file_path.resolve().relative_to(repo_root.resolve())
        parts = list(rel_path.parts)

        # Remove PDF, TEX, or recent from the path if present
        if parts and parts[0] in ('PDF', 'TEX', 'recent'):
            parts = parts[1:]

        return Path(*parts) if parts else Path('.')
    except ValueError:
        # File is not relative to repo_root
        return file_path


def get_mirror_paths(source_file: Path, repo_root: Optional[Path]) -> dict[str, Optional[Path]]:
    """Get mirrored paths for PDF and TEX outputs.

    Args:
        source_file: Path to the source markdown file
        repo_root: Repository root path (None for simple mode)

    Returns:
        Dictionary with 'pdf', 'tex', and 'recent' paths
    """
    if repo_root is None:
        # Simple mode: outputs in same directory as source
        return {
            'pdf': source_file.with_suffix('.pdf'),
            'tex': source_file.with_suffix('.tex'),
            'recent': None
        }

    # Get relative path from repo root
    rel_path = get_relative_path_from_root(source_file, repo_root)

    # Build mirrored paths
    pdf_path = repo_root / 'PDF' / rel_path.with_suffix('.pdf')
    tex_path = repo_root / 'TEX' / rel_path.with_suffix('.tex')
    recent_dir = repo_root / 'recent'

    return {
        'pdf': pdf_path,
        'tex': tex_path,
        'recent': recent_dir
    }


def convert_md_to_tex(input_md: Path, output_tex: Path) -> bool:
    """Convert Markdown to LaTeX using Pandoc with Mermaid filter.

    Args:
        input_md: Path to input Markdown file
        output_tex: Path to output LaTeX file

    Returns:
        True if conversion succeeded, False otherwise
    """
    print(f"Converting Markdown to LaTeX...")

    # Ensure output directory exists
    output_tex.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [
                "pandoc",
                str(input_md),
                "--from=markdown",
                "--to=latex",
                "--standalone",
                "--filter", "pandoc-mermaid",
                "-o", str(output_tex)
            ],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"  ✓ LaTeX: {output_tex}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error converting Markdown to LaTeX:", file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        return False


def convert_md_to_pdf_direct(input_md: Path, output_pdf: Path) -> bool:
    """Convert Markdown directly to PDF using Pandoc (skip intermediate TEX).

    Args:
        input_md: Path to input Markdown file
        output_pdf: Path to output PDF file

    Returns:
        True if conversion succeeded, False otherwise
    """
    print(f"Converting Markdown directly to PDF...")

    # Ensure output directory exists
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [
                "pandoc",
                str(input_md),
                "--from=markdown",
                "--filter", "pandoc-mermaid",
                "-o", str(output_pdf)
            ],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"  ✓ PDF: {output_pdf}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error converting Markdown to PDF:", file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        return False


def compile_tex_to_pdf(tex_file: Path, output_pdf: Path) -> bool:
    """Compile LaTeX to PDF using latexmk.

    Args:
        tex_file: Path to LaTeX file
        output_pdf: Path where PDF should be placed

    Returns:
        True if compilation succeeded, False otherwise
    """
    print(f"Compiling LaTeX to PDF...")

    # Ensure output directory exists
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    # Create a temporary directory for compilation
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        temp_tex = tmpdir_path / tex_file.name

        # Copy TEX file to temp directory
        shutil.copy(tex_file, temp_tex)

        # Copy mermaid-images if they exist (created during pandoc conversion)
        mermaid_src = Path.cwd() / "mermaid-images"
        if mermaid_src.exists():
            mermaid_dst = tmpdir_path / "mermaid-images"
            shutil.copytree(mermaid_src, mermaid_dst)

        try:
            result = subprocess.run(
                [
                    "latexmk",
                    "-xelatex",
                    "-interaction=nonstopmode",
                    "-output-directory=" + str(tmpdir_path),
                    temp_tex.name
                ],
                cwd=tmpdir_path,
                capture_output=True,
                check=True
            )

            # Move generated PDF to final location
            temp_pdf = tmpdir_path / temp_tex.with_suffix('.pdf').name
            shutil.move(temp_pdf, output_pdf)

            print(f"  ✓ PDF: {output_pdf}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Error compiling LaTeX to PDF:", file=sys.stderr)
            if e.stderr:
                # Decode with error handling for non-UTF8 output
                stderr_text = e.stderr.decode('utf-8', errors='replace')
                print(stderr_text, file=sys.stderr)
            return False


def copy_to_recent(source_file: Path, recent_dir: Path, file_type: str):
    """Copy file to recent/ folder for quick access.

    Args:
        source_file: Source file to copy
        recent_dir: recent/ directory path
        file_type: Type of file ('pdf' or 'tex')
    """
    if not source_file.exists():
        return

    recent_dir.mkdir(parents=True, exist_ok=True)
    dest_file = recent_dir / source_file.name

    shutil.copy(source_file, dest_file)
    print(f"  → recent/{source_file.name}")


def build_markdown_outputs(
    source_file: Path,
    mode: Literal['both', 'pdf-only', 'tex-only'],
    repo_root: Optional[Path]
) -> bool:
    """Build outputs from markdown source.

    Args:
        source_file: Path to markdown source file
        mode: Output mode ('both', 'pdf-only', 'tex-only')
        repo_root: Repository root (None for simple mode)

    Returns:
        True if build succeeded, False otherwise
    """
    paths = get_mirror_paths(source_file, repo_root)

    print(f"\nBuilding from: {source_file}")
    if repo_root:
        print(f"Repository: {repo_root}")

    success = True

    if mode == 'pdf-only':
        # Direct MD → PDF (skip TEX)
        if not convert_md_to_pdf_direct(source_file, paths['pdf']):
            return False
        if paths['recent']:
            copy_to_recent(paths['pdf'], paths['recent'], 'pdf')

    elif mode == 'tex-only':
        # MD → TEX only
        if not convert_md_to_tex(source_file, paths['tex']):
            return False
        if paths['recent']:
            copy_to_recent(paths['tex'], paths['recent'], 'tex')

    else:  # mode == 'both'
        # MD → TEX → PDF
        if not convert_md_to_tex(source_file, paths['tex']):
            return False

        if not compile_tex_to_pdf(paths['tex'], paths['pdf']):
            return False

        if paths['recent']:
            copy_to_recent(paths['tex'], paths['recent'], 'tex')
            copy_to_recent(paths['pdf'], paths['recent'], 'pdf')

    return True


def main():
    """Main entry point for the marktex CLI."""
    parser = argparse.ArgumentParser(
        description="Convert Markdown files with Mermaid diagrams to LaTeX and PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  marktex my-notes.md                    # Generate both .tex and .pdf
  marktex my-notes.md --pdf-only         # Generate only .pdf
  marktex my-notes.md --tex-only         # Generate only .tex
  marktex my-notes.md --repo-root .      # Use mirrored PDF/ and TEX/ folders
  marktex --check-deps                   # Check if dependencies are installed

Output Modes:
  Default: Generate both .tex and .pdf files
  --pdf-only: Skip .tex intermediate, generate .pdf directly (faster)
  --tex-only: Generate only .tex file, skip PDF compilation

Folder Organization:
  If PDF/ and TEX/ folders exist (or --repo-root specified), outputs are
  organized in mirrored folder structure with recent/ for quick access.

Requirements:
  - pandoc
  - pandoc-mermaid filter
  - latexmk (from texlive)
  - mermaid-cli (mmdc)
        """
    )

    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Input Markdown file"
    )

    parser.add_argument(
        "--pdf-only",
        action="store_true",
        help="Generate only PDF (skip .tex intermediate)"
    )

    parser.add_argument(
        "--tex-only",
        action="store_true",
        help="Generate only .tex file (skip PDF compilation)"
    )

    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root for mirrored folder structure (auto-detected if not specified)"
    )

    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Check if all required dependencies are installed"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="marktex 0.2.0"
    )

    args = parser.parse_args()

    # Check dependencies if requested
    if args.check_deps:
        all_found, missing = check_dependencies()
        if all_found:
            print("✓ All dependencies are installed!")
            return 0
        else:
            print("✗ Missing dependencies:", file=sys.stderr)
            for dep in missing:
                print(f"  - {dep}", file=sys.stderr)
            return 1

    # Validate input file
    if not args.input:
        parser.print_help()
        return 1

    input_file = args.input.resolve()
    if not input_file.exists():
        print(f"Error: file not found: {input_file}", file=sys.stderr)
        return 1

    if not input_file.is_file():
        print(f"Error: not a file: {input_file}", file=sys.stderr)
        return 1

    # Check dependencies before proceeding
    all_found, missing = check_dependencies()
    if not all_found:
        print("✗ Missing required dependencies:", file=sys.stderr)
        for dep in missing:
            print(f"  - {dep}", file=sys.stderr)
        print("\nRun 'marktex --check-deps' for more information.", file=sys.stderr)
        return 1

    # Validate mutually exclusive flags
    if args.pdf_only and args.tex_only:
        print("Error: --pdf-only and --tex-only are mutually exclusive", file=sys.stderr)
        return 1

    # Determine output mode
    if args.pdf_only:
        mode = 'pdf-only'
    elif args.tex_only:
        mode = 'tex-only'
    else:
        mode = 'both'

    # Determine source type (future-proof for Phase 2)
    try:
        source_type = determine_source_type(input_file)
    except (NotImplementedError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Find repository root (auto-detect or use provided)
    if args.repo_root:
        repo_root = args.repo_root.resolve()
        if not repo_root.is_dir():
            print(f"Error: --repo-root must be a directory: {repo_root}", file=sys.stderr)
            return 1
    else:
        repo_root = find_repo_root(input_file.parent)

    # Build outputs (Phase 1: only markdown supported)
    if source_type == 'markdown':
        success = build_markdown_outputs(input_file, mode, repo_root)
    # elif source_type == 'latex':  # Phase 2
    #     success = build_pdf_from_tex(input_file, repo_root)

    if success:
        print("\n✓ Done!")
        return 0
    else:
        print("\n✗ Build failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
