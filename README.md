# openstack compose
尝试以类似docker-compose的方式管理openstack VMs。  
目前只支持通过yaml配置文件一键构建项目和清理项目。  

> 需要通过环境变量提供openstack集群连接信息。

欢迎试用！
## 使用示例
配置文件示例：
```
project:
  name: test_project
  description: 测试项目
  vm:
  # name为VM实例的名字
  - name: vm-1
  # image为启动VM的镜像名
    image: tests-WEB2-Weblogic_RCE
    # flavor为VM要使用的配额名
    flavor: 2m4g80
    # IP地址指定要绑定到VM实例的ip地址列表，可以指定多个，必须是CIDR形式
    ip_address: 
    - 172.26.4.54/24
    - 172.26.3.27/24
    # 浮动IP要指定需要绑定浮动IP的网卡ip, 比如下面要在172.16.4.54的网卡上绑定浮动IP
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
python os_compose.py up -c <yaml配置文件>
```

清理项目
```
python os_compose.py down -c <yaml配置文件>
```