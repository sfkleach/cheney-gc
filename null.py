class Null:
    """
    Null objects ignore all operations with no side effects.
    """

    def __getattr__(self, name):
        def null(*args, **kwargs):
            pass
        return null
    
    def __setattr__(self, name, value):
        pass

    def __delattr__(self, name):
        pass

    def __call__(self, *args, **kwargs):
        return self
    
    def __enter__(self):
        pass
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def __str__(self, *args, **kwargs):
        return "Null"
