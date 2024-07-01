try:
    import coverage
    coverage.process_startup()
except ImportError:
    pass
