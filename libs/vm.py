import os
import netaddr
class VM:
    name = ''
    image = ''
    flavor = ''
    server = ''
    float_ip = ''
    allow_ports = [22,80,443,445,3389,8080,5901]
    sec_group = []
    def __init__(self,cfg:dict) -> None:
        self.ip_address = []
        self.networks = []
        self.name = cfg['name']
        self.image = cfg['image']
        self.flavor = cfg['flavor']
        self.have_float_ip = 'no'
        self.config_driver = False
        self.script = ''
        self.script_file = ''
        #self.allow_ports = cfg['ports']
        if 'ip_address' in cfg.keys():
            for ip in cfg['ip_address']:
                self.ip_address.append(netaddr.IPNetwork(ip))
        if 'float_ip' in cfg.keys():
            self.have_float_ip = 'yes'
            self.float_ip_bind = cfg['float_ip']
        if 'config_driver' in cfg.keys():
            self.config_driver = cfg['config_driver']
        if 'script' in cfg.keys():
            self.script_file = cfg['script']
            with open(os.path.join('scripts',self.script_file),'r') as fsc:
                self.script = fsc.read()
    def update(self, server) -> None:
        """接受创建的server对象"""
        self.server = server