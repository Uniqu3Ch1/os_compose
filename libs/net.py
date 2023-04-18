class Net:
    name = ''
    ip_range = ''
    cidr = ''
    subnet = ''
    network = ''
    allow_ports = [22,80,443,445,3389,8080,5901]


    def __init__(self,cfg:dict) -> None:
        self.name = cfg['name']
        self.ip_range = cfg['ip_range']
        self.allow_ports = cfg['ports']
    
    def update(self) -> None:
        """接受创建的Network对象"""
        pass