"""
读取 YAML 配置文件并创建 VM
"""
import os
import netaddr
import openstack
import yaml

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

        # 等待 VM 启动并获取 IP 地址
        server = conn.compute.wait_for_server(server)
        #network = conn.network.find_network(name_or_id=net_id)
        ip_address = server.addresses

        # 打印 VM IP 地址
        print(f"Created VM {name} with IP address {ip_address} and password: {server.admin_password}")
    except openstack.exceptions.BadRequestException as error:
        print(error)
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

        # 等待 VM 启动并获取 IP 地址
        server = conn.compute.wait_for_server(server)
        #network = conn.network.find_network(name_or_id=net_id)
        ip_address = server.addresses

        # 打印 VM IP 地址
        print(f"Created VM {name} with IP address {ip_address} and password: {server.admin_password}")


def create_subnet(conn, network, cidr_prefix, gw_ip, dhcp_ip_range):
    """定义创建 Subnet 的函数，将需要动态计算 CIDR 的变量作为参数传递"""
    # 连接 OpenStack


    # 设定 DHCP IP 地址的数量，这里给出的是 10.0.0.2~10.0.0.254 地址池大小
    dhcp_ips = len(netaddr.IPNetwork(dhcp_ip_range)) - 1

    # 设定Subnet 的掩码
    cidr = netaddr.IPNetwork(cidr_prefix)
    mask_bits = cidr.prefixlen
    subnet_mask = netaddr.IPAddress((1 << 32) - (1 << 32 - mask_bits))

    # 计算 Subnet 网段和广播地址
    subnet_start = netaddr.IPAddress(cidr.network + 1)
    subnet_end = netaddr.IPAddress(cidr.broadcast - 2)

    # 根据掩码位和 IP 范围大小计算 DHCP 可用 IP 地址
    dhcp_start = netaddr.IPAddress(
        cidr.network + 2
    )
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


def find_subnet(connection, cidr):
    """根据传入的cidr在当前项目中查找subnet, 如果找不到就抛出NotFoundException"""

    subnets = connection.network.subnets(project_id=connection.session.get_project_id())
    subnet_list = list(subnets)
    for _subnet in subnet_list:
        if _subnet.cidr == cidr:
            return _subnet
    raise openstack.exceptions.NotFoundException

def create_router(connection, subnets, external_network_name=None):
    """创建路由，连接指定子网"""
    router_name = 'auto-created-router'
    if external_network_name != None:
        external_network = connection.network.find_network(external_network_name)
        router = connection.network.create_router(name=router_name, external_gateway_info={'network_id': external_network.id})
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



def main():
    """读取 YAML 配置文件并创建 VM"""

    with open("vm-config.yaml", "r", encoding="utf8") as yaml_config:
        vm_configs = yaml.safe_load(yaml_config)

    project_name = vm_configs['project']['name']
    # 连接 OpenStack，创建一个空 subnet_id 列表以存储创建的子网 ID
    admin_connection = openstack.connect(**auth_args)
    subnets = {}
    # 可互通网络列表
    interoperable = []

    # 创建指定项目，并返回新项目的连接对象
    connection, project = create_project(admin_connection, project_name)
    
    # 从配置文件中读取网络信息
    network_config = vm_configs['project']['nets']

    # 处理虚拟机配置
    for config in vm_configs['project']['vm']:
        networks = []
        # 处理虚拟机网络配置
        vmnet_list = [net_name for net_name in config['net']]

        # 遍历配置文件中的net列表，获取 IP 地址和掩码
        for vmnet in vmnet_list:
            ip_net = netaddr.IPNetwork(network_config[vmnet]["ip_addr"])
    
            cidr_prefix = str(ip_net.cidr)

            # 检查子网是否存在，如果不存在则创建
            try:
                subnet = find_subnet(connection, cidr_prefix)
            except openstack.exceptions.NotFoundException:
                network_name = f"auto-created-network-{cidr_prefix}"
                network = connection.network.create_network(name=network_name)

                gw_ip = str(netaddr.IPAddress(ip_net.first + 254))

                dhcp_ip_range = str(
                    netaddr.IPNetwork(
                        f'{netaddr.IPAddress(ip_net.first + 2)}/{ip_net.prefixlen}'
                        )
                )
                subnet = create_subnet(
                    connection, network, cidr_prefix, gw_ip, dhcp_ip_range
                    )

            # 将子网对象添加到 subnets 列表中
            subnets[str(ip_net)] = subnet
            networks.append({"uuid": subnet.network_id, "fixed_ip": ip_net.ip})

            

        # 2.创建 VM
        create_vm(
            conn=connection,
            name=config["name"],
            image=config["image"],
            flavor=config["flavor"],
            networks=networks
        )

    # 3.根据网络配置创建路由
    for net_name in network_config.keys():
        net = network_config[net_name]
        if 'connect' in net.keys():
            ipaddr = net['ip_addr']
            interoperable.append(subnets[ipaddr])

    create_router(connection, interoperable,'provider')



if __name__ == '__main__':
    main()
    