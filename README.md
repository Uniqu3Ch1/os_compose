# openstack compose
尝试以类似docker-compose的方式管理openstack VMs。
# 使用示例
配置文件示例：
```
project:
  name: test_project
  description: 测试项目
  vm:
  - name: vm-1
    image: tests-WEB2-Weblogic_RCE
    flavor: 2m4g80
    ip_address: 
    - 172.26.4.54/24
    - 172.26.3.27/24
    float_ip: 172.26.4.54
  - name: kali-attacker
    image: YJ-kali-linux-2020.1-live-amd64
    flavor: 2m4g
    ip_address:
    - 172.26.2.35/24
    float_ip: 172.26.2.35
  - name: vm-2
    image: YJ-Struts2-052-RCE
    flavor: 2m4g80
    ip_address:
    - 172.26.3.75/24
  - name: vm-3
    image: YJ-ThinkCMF-FileInclude
    flavor: 2m4g80
    ip_address: 
    - 172.26.4.22/24
  - name: vm-4
    image: YJ-Thinkphp5.1~5.2_RCE
    flavor: 2m4g80
    ip_address:
    - 172.26.3.23/24
    - 172.26.2.182/24

```
安装依赖
> pip install python-openstackclient==6.2.0

构建项目
```
python os_compose.py up
```

清理项目
```
python os_compose.py down
```