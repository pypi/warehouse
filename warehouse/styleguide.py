import ast


class FlaskSessionCheck(object):
    CODE = 'E498'
    ERROR_TEXT = 'Using Flask sessions is not allowed!'
    name = 'FlaskSessionCheck'
    version = '0.1.0'

    @classmethod
    def error_text(cls):
        return '{} {}'.format(cls.CODE, cls.ERROR_TEXT)

    def __init__(self, tree, filename):
        self.tree = tree
        self.filename = filename

    def run(self):
        # PEP8 expects yields of (lineno, offset, text, <ignored>)
        def error_from_leaf(leaf):
            return (leaf.lineno, leaf.col_offset, self.error_text(), None)

        for leaf in self.tree.body:
            if not isinstance(leaf, (ast.Import, ast.ImportFrom)):
                continue

            import_names = [alias.name for alias in leaf.names]

            if isinstance(leaf, ast.Import):
                if 'flask.session' in import_names:
                    yield error_from_leaf(leaf)
            elif isinstance(leaf, ast.ImportFrom):
                if leaf.module == 'flask' and 'session' in import_names:
                    yield error_from_leaf(leaf)
