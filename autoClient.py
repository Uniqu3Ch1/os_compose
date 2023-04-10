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
def create_vm(conn, name, image, flavor, net_id, ip_address):
    """根据传入的name、image、flavor、subnet_id、ip地址创建VM"""

    # 连接 OpenStack
    connection = openstack.connect(**auth_args)

    # 获取镜像和配额对象
    image_obj = connection.compute.find_image(image)
    flavor_obj = connection.compute.find_flavor(flavor)

    # 创建 VM
    server = connection.compute.create_server(
        name=name,
        image_id=image_obj.id,
        flavor_id=flavor_obj.id,
        networks=[{"uuid": net_id, "fixed_ip": ip_address}],
    )

    # 等待 VM 启动并获取 IP 地址
    server = conn.compute.wait_for_server(server)
    network = conn.network.find_network(name_or_id=net_id)
    ip_address = server.addresses[network.name][0]["addr"]

    # 打印 VM IP 地址
    print(f"Created VM {name} with IP address {ip_address}")



def create_subnet(network, cidr_prefix, gw_ip, dhcp_ip_range):
    """定义创建 Subnet 的函数，将需要动态计算 CIDR 的变量作为参数传递"""
    # 连接 OpenStack
    conn = openstack.connect(**auth_args)

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
    for _subnet in subnets:
        if _subnet.cidr == cidr:
            return _subnet
    raise openstack.exceptions.NotFoundException


def main():
    """读取 YAML 配置文件并创建 VM"""

    with open("vm-config.yaml", "r", encoding="utf8") as yaml_config:
        vm_configs = yaml.safe_load(yaml_config)

    # 连接 OpenStack，创建一个空 subnet_id 列表以存储创建的子网 ID
    connection = openstack.connect(**auth_args)
    subnet_ids = []

    # 处理所有配置
    for config in vm_configs:
        # 获取 IP 地址和掩码
        ip_net = netaddr.IPNetwork(config["ip_addr"])
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
            subnet = create_subnet(network, cidr_prefix, gw_ip, dhcp_ip_range)


        subnet_id = subnet.id

        # 将子网 ID 添加到 subnet_ids 列表中
        subnet_ids.append(subnet_id)

        # 创建 VM
        create_vm(
            conn=connection,
            name=config["name"],
            image=config["image"],
            flavor=config["flavor"],
            net_id=subnet.network_id,
            ip_address=str(ip_net.ip),
        )


def clean_subnets(conn, subnet_ids):
    """删除创建的子网（仅为示例，生产环境中不建议删除子网）"""

    for subnet_id in subnet_ids:
        conn.network.delete_subnet(subnet_id)

if __name__ == '__main__':
    main()
    