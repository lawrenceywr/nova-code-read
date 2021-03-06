#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2017/5/27 17:31
# @Author  : LawrenceYang
# @Site    : 
# @File    : run_instance.py
# @Software: PyCharm

创建虚拟机的源码分析

CLI
nova boot --flavor 2 --image 226bc6e5-60d7-4a2c-bf0d-a568a1e26e00 vm2

#//nova/compute/api.py
    def _create_instance(self, context, instance_type,
               image_href, kernel_id, ramdisk_id,
               min_count, max_count,
               display_name, display_description,
               key_name, key_data, security_groups,
               availability_zone, user_data, metadata,
               injected_files, admin_password,
               access_ip_v4, access_ip_v6,
               requested_networks, config_drive,
               block_device_mapping, auto_disk_config,
               reservation_id=None, scheduler_hints=None,
               legacy_bdm=True):
        """Verify all the input parameters regardless of the provisioning
        strategy being performed and schedule the instance(s) for
        creation.
        """
        """定义一个create_instance的私有方法
        """

        # Normalize and setup some parameters
        # 如果没有UUID则调用nova/utils.py中generate_uid方法生成一个UUID
        if reservation_id is None:
            reservation_id = utils.generate_uid('r')
        security_groups = security_groups or ['default']
        min_count = min_count or 1
        max_count = max_count or min_count
        block_device_mapping = block_device_mapping or []

        # 从配置文件中读取默认flavor
        if not instance_type:
            instance_type = flavors.get_default_flavor()

        # 根据传进来的镜像来设置镜像的ID和boot_meta
        if image_href:
            image_id, boot_meta = self._get_image(context, image_href)
        else:
            image_id = None
            boot_meta = {}
            boot_meta['properties'] = \
                self._get_bdm_image_metadata(context,
                    block_device_mapping, legacy_bdm)

        self._check_auto_disk_config(image=boot_meta,
                                     auto_disk_config=auto_disk_config)

        # 确认创建在哪一台主机上
        handle_az = self._handle_availability_zone
        availability_zone, forced_host, forced_node = handle_az(context,
                                                            availability_zone)

        # 根据输入参数，生成主机的配置，并且对一些参数进行验证，有异常则抛出
        base_options, max_net_count = self._validate_and_build_base_options(
                context,
                instance_type, boot_meta, image_href, image_id, kernel_id,
                ramdisk_id, display_name, display_description,
                key_name, key_data, security_groups, availability_zone,
                forced_host, user_data, metadata, injected_files, access_ip_v4,
                access_ip_v6, requested_networks, config_drive,
                block_device_mapping, auto_disk_config, reservation_id,
                max_count)

        # max_net_count is the maximum number of instances requested by the
        # user adjusted for any network quota constraints, including
        # consideration of connections to each requested network
        #
        if max_net_count == 0:
            raise exception.PortLimitExceeded()
        elif max_net_count < max_count:
            LOG.debug(_("max count reduced from %(max_count)d to "
                        "%(max_net_count)d due to network port quota"),
                       {'max_count': max_count,
                        'max_net_count': max_net_count})
            max_count = max_net_count

        block_device_mapping = self._check_and_transform_bdm(
            base_options, boot_meta, min_count, max_count,
            block_device_mapping, legacy_bdm)

        # 创建虚拟机对象，并写入数据库
        instances = self._provision_instances(context, instance_type,
                min_count, max_count, base_options, boot_meta, security_groups,
                block_device_mapping)
        # scheduler需要用的过滤选项
        filter_properties = self._build_filter_properties(context,
                scheduler_hints, forced_host, forced_node, instance_type)

        self._update_instance_group(context, instances, scheduler_hints)
        #14060857 add for relative group scheduler hints
        self._update_instance_relative_group(context, instances, scheduler_hints)

        # 将数据库中的实例状态设置为start
        for instance in instances:
            self._record_action_start(context, instance,
                                      instance_actions.CREATE)

        self.compute_task_api.build_instances(context,
                instances=instances, image=boot_meta,
                filter_properties=filter_properties,
                admin_password=admin_password,
                injected_files=injected_files,
                requested_networks=requested_networks,
                security_groups=security_groups,
                block_device_mapping=block_device_mapping,
                legacy_bdm=False)

        return (instances, reservation_id)

