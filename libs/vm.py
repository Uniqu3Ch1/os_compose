import netaddr
class VM:
    name = ''
    image = ''
    flavor = ''
    server = ''
    float_ip = ''
    def __init__(self,cfg:dict) -> None:
        self.ip_address = []
        self.networks = []
        self.name = cfg['name']
        self.image = cfg['image']
        self.flavor = cfg['flavor']
        if 'ip_address' in cfg.keys():
            for ip in cfg['ip_address']:
                self.ip_address.append(netaddr.IPNetwork(ip))
        if 'float_ip' in cfg.keys():
            self.have_float_ip = 'yes'
            self.float_ip_bind = cfg['float_ip']
    def update(self, server) -> None:
        """接受创建的server对象"""
        self.server = server