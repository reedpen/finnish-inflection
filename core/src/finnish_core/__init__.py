"""Finnish inflection logic shared by the CLI and other front ends.

The library does no printing, file, network, or clock access of its own:
callers inject the morphology model, time, and randomness.
"""
