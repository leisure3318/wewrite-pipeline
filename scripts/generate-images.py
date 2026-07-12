#!/usr/bin/env python3
"""Backwards-compatible generic entry point for image generation."""

from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("generate-images-myweb3.py")), run_name="__main__")
