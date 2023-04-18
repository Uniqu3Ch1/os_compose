"""
解析YAML配置文件, 创建config对象
"""
import yaml
from libs.vm import VM

class Config:
    def __init__(self, filename='vm-config.yaml') -> None:
        """解析YAML配置文件"""
        try:
            with open(filename, "r", encoding="utf8") as yaml_config:
                self.project = yaml.safe_load(yaml_config)['project']
            self.vm_cfgs = self.project['vm']
            # 从配置文件中读取网络信息
            #self.network_cfgs = self.project['nets']
            self.project_name = self.project['name']
            self.project_description = self.project['description']
        except KeyError as err:
            print(f'WARNING {err} is missing!')


    def parse_vm(self) -> list[VM]:
        """根据配置文件, 创建VM对象"""
        vm_list = []
        for vm_cfg in self.vm_cfgs:
            vm = VM(vm_cfg)
            vm_list.append(vm)
        return vm_list
   