class BaseAdapter(object):

    def __init__(self, *args, **kwargs):
        super(BaseAdapter, self).__init__(*args, **kwargs)
        self.model = None

    def __get__(self, instance, type=None):
        if instance is not None:
            raise AttributeError(
                "Manager isn't accessible via %s instances" % type.__name__)
        return self

    def contribute_to_class(self, model, name):
        # TODO: Use weakref because of possible memory leak / circular
        #   reference.
        self.model = model

        # Add ourselves to the Model class
        setattr(model, name, self)
