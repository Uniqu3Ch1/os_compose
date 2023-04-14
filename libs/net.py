class Net:
    name = ''
    ip_range = ''
    cidr = ''
    subnet = ''
    network = ''


    def __init__(self,cfg:dict) -> None:
        self.name = cfg['name']
        self.ip_range = cfg['ip_range']
    
    def update(self) -> None:
        """接受创建的Network对象"""
        pass