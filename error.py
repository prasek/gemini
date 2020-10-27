class ApiError(Exception):
    def __init__(self, res):
        self.res = res
        self.code = res.status_code
        self.json = res.json()
        super().__init__({"code": res.status_code, "json": res.json()})


