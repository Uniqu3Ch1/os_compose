"""
读取 YAML 配置文件并创建 VM
"""
import os
import sys
import netaddr
import argparse
import openstack
from libs.config import Config


# 配置 OpenStack 连接信息
auth_args = {
    "auth_url": os.environ["OS_AUTH_URL"],
    "project_name": os.environ["OS_PROJECT_NAME"],
    "project_domain_id": os.environ["OS_PROJECT_ID"],
    "username": os.environ["OS_USERNAME"],
    "user_domain_name": os.environ["OS_USER_DOMAIN_NAME"],
    "password": os.environ["OS_PASSWORD"],
}


# 定义创建 VM 的函数
def create_vm(conn, vm_cfg, networks):
    """根据传入的name、image、flavor、subnet_id、ip地址创建VM"""
    print('正在创建虚拟机...')
    try:
        # 获取镜像和配额对象
        image_obj = conn.compute.find_image(vm_cfg.image)
        flavor_obj = conn.compute.find_flavor(vm_cfg.flavor)

        # 创建 VM
        server = conn.compute.create_server(
            name=vm_cfg.name,
            image_id=image_obj.id,
            flavor_id=flavor_obj.id,
            networks=networks,
            #networks=[{"uuid": net_id, "fixed_ip": ip_address}],
            security_groups=[{'name': vm_cfg.sec_group[0].name}]
        )
    except openstack.exceptions.BadRequestException as err: # type: ignore
        #print('ip 地址重复, 尝试分配新ip...')
        print(err)
        # 获取镜像和配额对象
        image_obj = conn.compute.find_image(vm_cfg.image)
        flavor_obj = conn.compute.find_flavor(vm_cfg.flavor)
        # 删除指定的ip地址
        for dic in networks:
            dic.pop('fixed_ip')

        # 创建 VM
        server = conn.compute.create_server(
            name=vm_cfg.name,
            image_id=image_obj.id,
            flavor_id=flavor_obj.id,
            networks=networks,
            #networks=[{"uuid": net_id, "fixed_ip": ip_address}],
            security_groups=[{'name': vm_cfg.sec_group[0].name}]
        )
    except openstack.exceptions.ResourceTimeout: # type: ignore
        print("Created VM waiting timeout")

    return server

def delete_vm(conn, vm_cfg):
    """删除已创建的虚拟机"""
    servers = conn.compute.servers()
    servers_dict = {server.name : server.id for server in servers}
    if vm_cfg.name in servers_dict.keys():
        conn.compute.delete_server(servers_dict[vm_cfg.name])
        print(f'虚拟机实例 {vm_cfg.name} 删除成功')
    else:
        print(f'虚拟机实例 {vm_cfg.name} 不存在')

def create_subnet(conn, network, cidr_prefix, gw_ip):
    """定义创建 Subnet 的函数，将需要动态计算 CIDR 的变量作为参数传递"""

    # 设定Subnet 的掩码
    cidr = netaddr.IPNetwork(cidr_prefix)
    #mask_bits = cidr.prefixlen
    #subnet_mask = netaddr.IPAddress((1 << 32) - (1 << 32 - mask_bits))

    # 计算 Subnet 网段和广播地址
    subnet_start = netaddr.IPAddress(cidr.network + 2)
    subnet_end = netaddr.IPAddress(cidr.broadcast - 2)

    # 根据掩码位和 IP 范围大小计算 DHCP 可用 IP 地址
    dhcp_start = subnet_start
    dhcp_end = subnet_end

    # 创建 Subnet
    subnet_name = f"auto-created-subnet-{cidr_prefix}"
    subnet = conn.network.create_subnet(
        name=subnet_name,
        ip_version=4,
        network_id=network.id,
        cidr=cidr_prefix,
        gateway_ip=gw_ip,
        allocation_pools=[{"start": str(dhcp_start), "end": str(dhcp_end)}],
    )

    return subnet

def delete_route_network(conn):
    """删除路由、网络和子网"""
    print('正在删除路由...')
    routers = list(conn.network.routers(project_id=conn.session.get_project_id()))
    if len(routers) == 0:
        print('路由不存在！')
    else:
        for port in conn.network.ports(device_id=routers[0].id):
            if port.network_id == '9107647b-c57b-475a-832a-79d8306089cb':
                continue
            # TODO: 端口可能占用无法删除
            conn.network.remove_interface_from_router(routers[0].id, port_id=port.id)
        conn.network.delete_router(routers[0])
    print('正在删除子网...')
    subnets = conn.network.subnets(project_id=conn.session.get_project_id())
    for subnet in subnets:
        conn.network.delete_subnet(subnet.id)
    print('子网删除完成...\n正在删除网络...')

    networks = conn.network.networks(project_id=conn.session.get_project_id())
    for network in networks:
        conn.network.delete_network(network.id)
    print('网络删除完成! ')


def find_net(connection, cidr):
    """根据传入的cidr在当前项目中查找subnet, 如果找不到就抛出NotFoundException"""
    subnets = connection.network.subnets(project_id=connection.session.get_project_id())
    subnet_list = list(subnets)
    for _subnet in subnet_list:
        if _subnet.cidr == cidr:
            network = connection.network.find_network(_subnet.network_id)
            return network, _subnet
    raise openstack.exceptions.NotFoundException # type: ignore

def create_router(connection, subnets, external_network_name=None):
    """创建路由，连接指定子网"""
    router_name = 'auto-created-router'
    if external_network_name is not None:
        external_network = connection.network.find_network(external_network_name)
        router = connection.network.create_router(
            name=router_name,
            external_gateway_info={'network_id': external_network.id}
            )
    else:
        router = connection.network.create_router(name=router_name)
    print(f"路由 {router.name} 创建完成, ID为: '{router.id}'")
    for subnet in subnets:
        connection.network.add_interface_to_router(router, subnet_id=subnet.id)
        print(f"连接子网 {subnet.name} 到路由 {router.name} ")
    return router



def create_project(connection, project_name=None, description=None):
    """创建指定project, 并将当前用户加入project"""
    print('正在创建项目...')
    try:
        project = connection.identity.create_project(name=project_name, description=description)
        admin = connection.identity.find_user(name_or_id=auth_args["username"])
        admin_role = connection.identity.find_role('admin')
        # 将当前用户加入新创建的project
        connection.identity.assign_project_role_to_user(project, admin, admin_role)

    except openstack.exceptions.ConflictException:
        print(f"{project_name} 已存在! 跳过创建...")
        project = connection.identity.find_project(name_or_id=project_name)


    new_auth_args = auth_args.copy()
    new_auth_args['project_name'] = project_name
    new_auth_args['project_id'] = project.id
    new_conn = openstack.connect(**new_auth_args)

    return new_conn, project



def delete_project(connection, project):
    """删除project"""
    connection.identity.delete_project(project)

def create_networks(connection, vm_config):
    """根据网络配置创建网络及子网,并返回openstack网络配置"""
    print('正在创建网络...')
    subnets = {}
    networks = []
    # 遍历配置文件中的net列表，获取 IP 地址和掩码
    for vm_ip in vm_config.ip_address:
        cidr_prefix = str(vm_ip.cidr)
        vm_config.cidr = cidr_prefix

        # 检查子网是否存在，如果不存在则创建
        try:
            network, subnet = find_net(connection, cidr_prefix)

        except openstack.exceptions.NotFoundException: # type: ignore
            network_name = f"auto-created-network-{cidr_prefix}"
            network = connection.network.create_network(name=network_name)
            # 计算网关ip
            gw_ip = str(netaddr.IPAddress(vm_ip.first + 254))


            subnet = create_subnet(connection, network, cidr_prefix, gw_ip)
        vm_config.networks.append(network)
        # 将子网对象添加到 subnets 列表中
        subnets[str(vm_ip.ip)] = subnet
        networks.append({"uuid": subnet.network_id, "fixed_ip": vm_ip.ip})

    return networks, subnets

def add_float_ip(connection, server, ipaddr):
    """根据配置信息找到需要绑定浮动ip的接口, 分配并绑定浮动ip"""
    # print(f'正在分配浮动ip 到 {server.name}')
    provider = connection.network.find_network(name_or_id='provider')
    floating_ip  = connection.network.create_ip(floating_network_id=provider.id)
    ports = connection.network.ports(device_id=server.id)
    for port in list(ports):
        ip_dict = port.fixed_ips[0]
        if ip_dict['ip_address'] == ipaddr:
            connection.network.update_ip(floating_ip, port_id=port.id)
    return floating_ip

def create_secgroup(connection, vm_onfig):
    """以默认配置创建安全组, 入站放通所有tcp端口"""
    sec_group = connection.network.find_security_group(name_or_id='os_compose',
        project_id=connection.session.get_project_id())
    if sec_group is None:
        sec_rule = {
            'description': 'auto created security group rule by os_compose',
            # 出站规则
            'direction': 'ingress',
            #: 可选项有 ``null``, ``tcp``, ``udp``, and ``icmp``.
            'protocol': 'tcp',
            #: The maximum port number in the range that is matched by the
            #: security group rule. The port_range_min attribute constrains
            #: the port_range_max attribute. If the protocol is ICMP, this
            #: value must be an ICMP type.
            'port_range_max': 65535,
            #: The minimum port number in the range that is matched by the
            #: security group rule. If the protocol is TCP or UDP, this value
            #: must be less than or equal to the value of the port_range_max
            #: attribute. If the protocol is ICMP, this value must be an ICMP type.
            'port_range_min': 1,
            'remote_ip_prefix': '0.0.0.0/0',
        }
        sec_group = connection.network.create_security_group(name='os_compose',
            description='auto created security group')
        #sec_rule['security_group_id'] = sec_group.id
        # allow all tcp port
        connection.network.create_security_group_rule(
            description=sec_rule['description'],
            security_group_id=sec_group.id,
            direction=sec_rule['direction'],
            protocol=sec_rule['protocol'],
            port_range_max=sec_rule['port_range_max'],
            port_range_min=sec_rule['port_range_min'],
            remote_ip_prefix=sec_rule['remote_ip_prefix'],
            )
        # allow all icmp 
        connection.network.create_security_group_rule(
            description=sec_rule['description'],
            security_group_id=sec_group.id,
            direction=sec_rule['direction'],
            protocol='icmp',
            port_range_max=sec_rule['port_range_max'],
            port_range_min=sec_rule['port_range_min'],
            remote_ip_prefix=sec_rule['remote_ip_prefix'],
            )
        
        # all all udp port
        connection.network.create_security_group_rule(
            description=sec_rule['description'],
            security_group_id=sec_group.id,
            direction=sec_rule['direction'],
            protocol='udp',
            port_range_max=sec_rule['port_range_max'],
            port_range_min=sec_rule['port_range_min'],
            remote_ip_prefix=sec_rule['remote_ip_prefix'],
            )
    vm_onfig.sec_group.append(sec_group)
    return sec_group


def up(filename='vm-config.yaml'):
    """读取 YAML 配置文件并创建 VM"""
    config = Config(filename)
    project_name = config.project_name
    project_description = config.project_description
    vm_list = config.parse_vm()

    # 连接 OpenStack，创建一个空 subnet_id 列表以存储创建的子网 ID
    admin_connection = openstack.connect(**auth_args)
    # 可互通网络列表
    interoperable = []
    # 创建指定项目，并返回新项目的连接对象
    connection, project = create_project(admin_connection, project_name, project_description)
    # 处理虚拟机配置
    for vm_config in vm_list:
        # 处理虚拟机网络配置
        networks, subnets = create_networks(connection,vm_config)
        # 创建安全组和默认安全组规则
        create_secgroup(connection, vm_config)
        # 2.创建 VM
        server = create_vm(
            conn=connection,
            vm_cfg=vm_config,
            networks=networks
        )
        vm_config.update(server)
        if hasattr(vm_config, 'float_ip_bind'):
            interoperable.append(subnets[vm_config.float_ip_bind])

    # 3.根据配置文件创建路由
    create_router(connection, interoperable,'provider')
    # 等待虚拟机创建完成，并打印相关信息
    #time.sleep(180)
    wait_and_print(connection, vm_list)


    print('openstack 项目构建完成!')

def wait_and_print(connection, vm_list):
    """等待虚拟机创建完成, 根据配置绑定浮动ip, 并打印相关信息"""
    print('正在等待虚拟机创建完成...')
    for vm_config in vm_list:
        try:
            server = connection.compute.wait_for_server(vm_config.server)
            if hasattr(vm_config, 'have_float_ip'):
                floatip = add_float_ip(connection, server, vm_config.float_ip_bind)
                ip_address = server.addresses
                vm_config.float_ip = floatip.floating_ip_address
                ip_list = [ip_address[net][0]['addr'] for net in ip_address.keys()]
                print(f"|{server.name}\t|\t{ip_list}:{vm_config.float_ip}\t|\t{server.admin_password}|")
            else:
                ip_address = server.addresses
                ip_list = [ip_address[net][0]['addr'] for net in ip_address.keys()]
                print(f"|{server.name}\t|\t{ip_list}\t|\t{server.admin_password}|")
        except openstack.exceptions.ResourceTimeout: # type: ignore
            print(f'{vm_config.server.name} 等待超时! ')
            if hasattr(vm_config, 'have_float_ip'):
                floatip = add_float_ip(connection, server, vm_config.float_ip_bind)
                ip_address = server.addresses
                vm_config.float_ip = floatip.floating_ip_address
                ip_list = [ip_address[net][0]['addr'] for net in ip_address.keys()]
                print(f"|{server.name}\t|\t{ip_list}:{vm_config.float_ip}\t|\t{server.admin_password}|")
            else:
                ip_address = server.addresses
                ip_list = [ip_address[net][0]['addr'] for net in ip_address.keys()]
                print(f"|{server.name}\t|\t{ip_list}\t|\t{server.admin_password}|")
            continue
        except openstack.exceptions.ResourceFailure as e:
            print(f'{vm_config.server.name} 创建失败! {e}')
            # TODO: 失败清理

def down(filename='vm-config.yaml'):
    """根据YAML配置文件清理项目"""
    config = Config(filename)
    project_name = config.project_name
    vm_list = config.parse_vm()

    admin_connection = openstack.connect(**auth_args)
    project = admin_connection.identity.find_project(name_or_id=project_name)
    auth_args['project_name'] = project_name
    auth_args['project_id'] = project.id
    new_conn = openstack.connect(**auth_args)
    for vm_cfg in vm_list:
        delete_vm(new_conn, vm_cfg)

    delete_route_network(new_conn)
    delete_project(admin_connection, project)
    print(f"项目 '{project_name}' 清理完成。")

def Usage():
    print(
"""
需要命令行参数！
Usage:
    os_compose: <action> [-c/--config config file]
        action: up/down 创建或删除openstack 项目
        -c/--config yaml配置文件路径
"""
    )

if __name__ == '__main__':
    if len(sys.argv) < 2:
        Usage()
        exit()
    parser = argparse.ArgumentParser(description='os_compose')
    parser.add_argument('action', type=str, help='要执行的动作：up/down')
    parser.add_argument('-c', '--config', type=str, help='配置文件路径')
    args = parser.parse_args()
    if args.action == 'up':
        up(args.config)
    elif args.action == 'down':
        down(args.config)
    else:
        print('无效参数，请重试')
    