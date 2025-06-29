#!/usr/bin/env python
"""
Main entry point for the TDDCoder application.
This script calls the main function from run_tdd_workflow.py.
"""
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from tdd_workflow.run_tdd_workflow import main


if __name__ == "__main__":
    main()
