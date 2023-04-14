"""
读取 YAML 配置文件并创建 VM
"""
import os
import time
import netaddr
import openstack
import yaml
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
def create_vm(conn, name, image, flavor, networks):
    """根据传入的name、image、flavor、subnet_id、ip地址创建VM"""
    print('正在创建虚拟机...')
    try:
        # 获取镜像和配额对象
        image_obj = conn.compute.find_image(image)
        flavor_obj = conn.compute.find_flavor(flavor)

        # 创建 VM
        server = conn.compute.create_server(
            name=name,
            image_id=image_obj.id,
            flavor_id=flavor_obj.id,
            networks=networks,
            #networks=[{"uuid": net_id, "fixed_ip": ip_address}],
        )
    except openstack.exceptions.BadRequestException as err:
        #print('ip 地址重复, 尝试分配新ip...')
        print(err)
        # 获取镜像和配额对象
        image_obj = conn.compute.find_image(image)
        flavor_obj = conn.compute.find_flavor(flavor)
        # 删除指定的ip地址
        for dic in networks:
            dic.pop('fixed_ip')

        # 创建 VM
        server = conn.compute.create_server(
            name=name,
            image_id=image_obj.id,
            flavor_id=flavor_obj.id,
            networks=networks,
            #networks=[{"uuid": net_id, "fixed_ip": ip_address}],
        )
    except openstack.exceptions.ResourceTimeout:
        print("Created VM waiting timeout")

    return server

def create_subnet(conn, network, cidr_prefix, gw_ip):
    """定义创建 Subnet 的函数，将需要动态计算 CIDR 的变量作为参数传递"""

    # 设定Subnet 的掩码
    cidr = netaddr.IPNetwork(cidr_prefix)
    #mask_bits = cidr.prefixlen
    #subnet_mask = netaddr.IPAddress((1 << 32) - (1 << 32 - mask_bits))

    # 计算 Subnet 网段和广播地址
    subnet_start = netaddr.IPAddress(cidr.network + 2)
    subnet_end = netaddr.IPAddress(cidr.broadcast - 1)

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


def find_net(connection, cidr):
    """根据传入的cidr在当前项目中查找subnet, 如果找不到就抛出NotFoundException"""

    subnets = connection.network.subnets(project_id=connection.session.get_project_id())
    subnet_list = list(subnets)
    for _subnet in subnet_list:
        if _subnet.cidr == cidr:
            network = connection.network.find_network(_subnet.network_id)
            return network, _subnet
    raise openstack.exceptions.NotFoundException

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
    print(f"Created router '{router.name}' with ID '{router.id}'")
    for subnet in subnets:
        connection.network.add_interface_to_router(router, subnet_id=subnet.id)
        print(f"Connected subnet '{subnet.name}' with ID '{subnet.id}' to router '{router.name}'")
    return router


def clean_subnets(conn, subnet_ids):
    """删除创建的子网（仅为示例，生产环境中不建议删除子网）"""

    for subnet_id in subnet_ids:
        conn.network.delete_subnet(subnet_id)

def create_project(connection, project_name=None):
    """创建指定project, 并将当前用户加入project"""
    print('正在创建项目...')
    try:
        project = connection.identity.create_project(name=project_name)
        admin = connection.identity.find_user(name_or_id=auth_args["username"])
        admin_role = connection.identity.find_role('admin')
        # 将当前用户加入新创建的project
        connection.identity.assign_project_role_to_user(project, admin, admin_role)

    except openstack.exceptions.ConflictException:
        print(f"{project_name} is exist! not create...")
        project = connection.identity.find_project(name_or_id=project_name)


    new_auth_args = auth_args.copy()
    new_auth_args['project_name'] = project_name
    new_auth_args['project_id'] = project.id
    new_conn = openstack.connect(**new_auth_args)

    return new_conn, project



def delete_project(connection, project_id):
    """删除project"""
    connection.identity.delete_project(project_id)

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

        except openstack.exceptions.NotFoundException:
            network_name = f"auto-created-network-{cidr_prefix}"
            network = connection.network.create_network(name=network_name)
            # 计算网关ip
            gw_ip = str(netaddr.IPAddress(vm_ip.first + 1))


            subnet = create_subnet(connection, network, cidr_prefix, gw_ip)
        vm_config.networks.append(network)
        # 将子网对象添加到 subnets 列表中
        subnets[str(vm_ip.ip)] = subnet
        networks.append({"uuid": subnet.network_id, "fixed_ip": vm_ip.ip})

    return networks, subnets

def add_float_ip(connection, server, ipaddr):
    provider = connection.network.find_network(name_or_id='provider')
    floating_ip  = connection.network.create_ip(floating_network_id=provider.id)
    ports = connection.network.ports(device_id=server.id)
    for port in list(ports):
        ip_dict = port.fixed_ips[0]
        if ip_dict['ip_address'] == ipaddr:
            connection.network.update_ip(floating_ip, port_id=port.id)
    return floating_ip

def main():
    """读取 YAML 配置文件并创建 VM"""
    config = Config()
    project_name = config.project_name
    vm_list = config.parse_vm()

    # 连接 OpenStack，创建一个空 subnet_id 列表以存储创建的子网 ID
    admin_connection = openstack.connect(**auth_args)
    # 可互通网络列表
    interoperable = []
    
    # 创建指定项目，并返回新项目的连接对象
    connection, project = create_project(admin_connection, project_name)
    # 处理虚拟机配置
    for vm_config in vm_list:
        # 处理虚拟机网络配置
        
        networks, subnets = create_networks(connection,vm_config)
        # 2.创建 VM
        server = create_vm(
            conn=connection,
            name=vm_config.name,
            image=vm_config.image,
            flavor=vm_config.flavor,
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
        server = connection.compute.wait_for_server(vm_config.server)
        if hasattr(vm_config, 'have_float_ip'):
            floatip = add_float_ip(connection, server, vm_config.float_ip_bind)
            ip_address = server.addresses
            vm_config.float_ip = floatip.floating_ip_address
            print(f"Created VM {server.name} with IP address {ip_address}:\
                {vm_config.float_ip} and password: {server.admin_password}")
        else:
            ip_address = server.addresses
            print(f"Created VM {server.name} with IP address {ip_address}\
                and password: {server.admin_password}")


if __name__ == '__main__':
    main()
    