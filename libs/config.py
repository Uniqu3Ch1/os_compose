import yaml
from libs.vm import VM

class Config:
    def __init__(self, filename='vm-config.yaml') -> None:
        """解析YAML配置文件"""
        with open(filename, "r", encoding="utf8") as yaml_config:
            self.project = yaml.safe_load(yaml_config)['project']
        self.vm_cfgs = self.project['vm']
        # 从配置文件中读取网络信息
        #self.network_cfgs = self.project['nets']
        self.project_name = self.project['name']

    def parse_vm(self) -> list:
        vm_list = []
        for vm_cfg in self.vm_cfgs:
            vm = VM(vm_cfg)
            vm_list.append(vm)
        return vm_list
    
"""     def parse_net(self) -> list:
        net_list = []
        for net_cfg in self.network_cfgs:
            net = Net(net_cfg)
            net_list.append(net)
        return net_list """


            


        


        