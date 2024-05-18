class staticproperty:
    def __init__(self, getter):
        self.getter = getter
        self.setter_func = None

    def __get__(self, obj, cls):
        return self.getter(cls)

    def __set__(self, obj, value):
        if self.setter_func is None:
            raise AttributeError("Setter not defined.")
        self.setter_func(obj.__class__, value)

    def setter(self, setter_func):
        self.setter_func = setter_func
        return self