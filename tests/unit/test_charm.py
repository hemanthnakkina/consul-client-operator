# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
from unittest.mock import patch

import pytest
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness

from charm import ConsulCharm


@pytest.fixture()
def harness():
    harness = Harness(ConsulCharm)
    harness.add_network("10.10.0.10")
    yield harness
    harness.cleanup()


@pytest.fixture()
def snap():
    with patch("charm.snap") as p:
        yield p


@pytest.fixture()
def read_config():
    with patch.object(ConsulCharm, "_read_configuration") as p:
        yield p


@pytest.fixture()
def write_config():
    with patch.object(ConsulCharm, "_write_configuration") as p:
        yield p


@pytest.fixture()
def connect_snap_interface():
    with patch.object(ConsulCharm, "_connect_snap_interface") as p:
        yield p


@pytest.fixture()
def write_tcp_check_script():
    with patch("config_builder.ConsulConfigBuilder._write_tcp_check_script") as p:
        yield p


def test_start(harness: Harness[ConsulCharm], snap):
    harness.begin_with_initial_hooks()
    assert harness.model.unit.status == BlockedStatus("Integration consul-cluster missing")


def test_consul_cluster_relation(harness: Harness[ConsulCharm], snap, read_config, write_config):
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]
    read_config.return_value = {
        "bind_addr": "10.10.0.10",
        "datacenter": datacenter,
        "ports": {
            "dns": -1,
            "http": -1,
            "https": -1,
            "grpc": -1,
            "grpc_tls": -1,
            "serf_lan": 8301,
            "serf_wan": -1,
            "server": 8300,
        },
        "retry_join": [join_server_addresses],
    }

    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )
    harness.begin_with_initial_hooks()
    assert harness.model.unit.status == ActiveStatus()


def test_consul_config_changed(harness: Harness[ConsulCharm], snap, read_config, write_config):
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]
    serf_lan_port = 9301

    harness.update_config({"serf-lan-port": serf_lan_port})
    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )
    harness.begin_with_initial_hooks()
    assert harness.model.unit.status == ActiveStatus()

    config = write_config.mock_calls[0].args[1]
    config = json.loads(config)
    assert config.get("ports", {}).get("serf_lan") == serf_lan_port


def test_consul_notify_socket_available(
    harness: Harness[ConsulCharm],
    snap,
    read_config,
    write_config,
    connect_snap_interface,
    write_tcp_check_script,
):
    """Test consul-notify relation socket available event."""
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]
    snap_name = "test-snap"
    socket_path = "data/socket.sock"

    read_config.return_value = {
        "bind_addr": "10.10.0.10",
        "datacenter": datacenter,
        "ports": {
            "dns": -1,
            "http": -1,
            "https": -1,
            "grpc": -1,
            "grpc_tls": -1,
            "serf_lan": 8301,
            "serf_wan": -1,
            "server": 8300,
        },
        "retry_join": [join_server_addresses],
    }

    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )

    _ = harness.add_relation(
        "consul-notify",
        "test-app",
        app_data={
            "snap_name": snap_name,
            "unix_socket_filepath": socket_path,
        },
    )

    harness.begin_with_initial_hooks()

    assert harness.model.unit.status == ActiveStatus()

    charm = harness.charm
    assert charm.consul_notify.snap_name == snap_name
    assert charm.consul_notify.unix_socket_filepath == socket_path

    connect_snap_interface.assert_called_with(charm.snap_name, snap_name, "consul-socket")
    assert connect_snap_interface.call_count >= 1

    assert write_config.called
    config = write_config.call_args[0][1]
    config_dict = json.loads(config)
    assert config_dict.get("enable_script_checks") is True
    assert "services" in config_dict

    services = config_dict["services"]
    assert len(services) == 1
    tcp_check_service = services[0]
    assert tcp_check_service["name"] == "tcp-health-check"
    assert tcp_check_service["check"]["id"] == "tcp-check"
    assert tcp_check_service["check"]["name"] == "TCP Health Check"
    assert "--socket-path" in tcp_check_service["check"]["args"]
    assert socket_path in tcp_check_service["check"]["args"]


def test_consul_notify_socket_gone(
    harness: Harness[ConsulCharm], snap, read_config, write_config, write_tcp_check_script
):
    """Test consul-notify relation socket gone event."""
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]
    snap_name = "test-snap"
    socket_path = "data/socket.sock"

    read_config.return_value = {
        "bind_addr": "10.10.0.10",
        "datacenter": datacenter,
        "ports": {
            "dns": -1,
            "http": -1,
            "https": -1,
            "grpc": -1,
            "grpc_tls": -1,
            "serf_lan": 8301,
            "serf_wan": -1,
            "server": 8300,
        },
        "retry_join": [join_server_addresses],
    }

    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )

    relation_id = harness.add_relation(
        "consul-notify",
        "test-app",
        app_data={
            "snap_name": snap_name,
            "unix_socket_filepath": socket_path,
        },
    )

    harness.begin_with_initial_hooks()

    charm = harness.charm
    assert charm.consul_notify.snap_name == snap_name
    assert charm.consul_notify.unix_socket_filepath == socket_path

    harness.remove_relation(relation_id)

    assert charm.consul_notify.unix_socket_filepath is None

    config = write_config.call_args[0][1]
    config_dict = json.loads(config)
    assert config_dict.get("enable_script_checks") is not True
    assert "services" not in config_dict or len(config_dict.get("services", [])) == 0


def test_consul_notify_relation_properties(
    harness: Harness[ConsulCharm], snap, read_config, write_config, write_tcp_check_script
):
    """Test consul-notify relation properties and is_ready functionality."""
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]
    snap_name = "test-snap"
    socket_path = "data/socket.sock"

    read_config.return_value = {
        "bind_addr": "10.10.0.10",
        "datacenter": datacenter,
        "ports": {
            "dns": -1,
            "http": -1,
            "https": -1,
            "grpc": -1,
            "grpc_tls": -1,
            "serf_lan": 8301,
            "serf_wan": -1,
            "server": 8300,
        },
        "retry_join": [join_server_addresses],
    }

    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )

    harness.begin_with_initial_hooks()

    charm = harness.charm
    assert not charm.consul_notify.is_ready

    harness.add_relation(
        "consul-notify",
        "test-app",
        app_data={
            "snap_name": snap_name,
            "unix_socket_filepath": socket_path,
        },
    )

    assert charm.consul_notify.is_ready
    assert charm.consul_notify.snap_name == snap_name
    assert charm.consul_notify.unix_socket_filepath == socket_path


def test_socket_config_persists_across_events(
    harness: Harness[ConsulCharm], snap, read_config, write_config, write_tcp_check_script
):
    """Test that socket configuration persists across subsequent charm events."""
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]
    snap_name = "test-snap"
    socket_path = "data/socket.sock"

    read_config.return_value = {
        "bind_addr": "10.10.0.10",
        "datacenter": datacenter,
        "ports": {
            "dns": -1,
            "http": -1,
            "https": -1,
            "grpc": -1,
            "grpc_tls": -1,
            "serf_lan": 8301,
            "serf_wan": -1,
            "server": 8300,
        },
        "retry_join": [join_server_addresses],
    }

    # Add consul-cluster relation
    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )

    # Add consul-notify relation with socket information
    harness.add_relation(
        "consul-notify",
        "test-app",
        app_data={
            "snap_name": snap_name,
            "unix_socket_filepath": socket_path,
        },
    )

    harness.begin_with_initial_hooks()
    charm = harness.charm

    # Verify socket configuration is present in initial config
    assert write_config.called
    initial_config = write_config.call_args[0][1]
    initial_config_dict = json.loads(initial_config)
    assert initial_config_dict.get("enable_script_checks") is True
    assert "services" in initial_config_dict
    assert len(initial_config_dict["services"]) == 1
    assert initial_config_dict["services"][0]["name"] == "tcp-health-check"
    assert "--socket-path" in initial_config_dict["services"][0]["check"]["args"]
    assert socket_path in initial_config_dict["services"][0]["check"]["args"]

    # Reset the mock to track subsequent calls
    write_config.reset_mock()

    # Trigger a config-changed event (this would have caused the bug)
    harness.update_config({"serf-lan-port": 8302})

    # Verify socket configuration is STILL present after config-changed
    # This is the key assertion that would fail with the bug
    if write_config.called:
        post_event_config = write_config.call_args[0][1]
        post_event_config_dict = json.loads(post_event_config)
        assert post_event_config_dict.get("enable_script_checks") is True
        assert "services" in post_event_config_dict
        assert len(post_event_config_dict["services"]) == 1
        assert post_event_config_dict["services"][0]["name"] == "tcp-health-check"
        assert "--socket-path" in post_event_config_dict["services"][0]["check"]["args"]
        assert socket_path in post_event_config_dict["services"][0]["check"]["args"]

    # Verify relation data is still accessible
    assert charm.consul_notify.is_ready
    assert charm.consul_notify.snap_name == snap_name
    assert charm.consul_notify.unix_socket_filepath == socket_path

    # Reset and trigger another event (upgrade-charm)
    write_config.reset_mock()
    harness.charm.on.upgrade_charm.emit()

    # Verify socket configuration persists after upgrade event
    if write_config.called:
        upgrade_config = write_config.call_args[0][1]
        upgrade_config_dict = json.loads(upgrade_config)
        assert upgrade_config_dict.get("enable_script_checks") is True
        assert "services" in upgrade_config_dict
        assert len(upgrade_config_dict["services"]) == 1
        assert upgrade_config_dict["services"][0]["name"] == "tcp-health-check"
        assert "--socket-path" in upgrade_config_dict["services"][0]["check"]["args"]
        assert socket_path in upgrade_config_dict["services"][0]["check"]["args"]


def test_tcp_health_check_disabled_by_config(
    harness: Harness[ConsulCharm], snap, read_config, write_config, write_tcp_check_script
):
    """Test that TCP health check is disabled when config option is set to False."""
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]
    snap_name = "test-snap"
    socket_path = "data/socket.sock"

    read_config.return_value = {
        "bind_addr": "10.10.0.10",
        "datacenter": datacenter,
        "ports": {
            "dns": -1,
            "http": -1,
            "https": -1,
            "grpc": -1,
            "grpc_tls": -1,
            "serf_lan": 8301,
            "serf_wan": -1,
            "server": 8300,
        },
        "retry_join": [join_server_addresses],
    }

    # Disable TCP health check via config
    harness.update_config({"enable-tcp-health-check": False})

    # Add consul-cluster relation
    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )

    # Add consul-notify relation with socket information
    harness.add_relation(
        "consul-notify",
        "test-app",
        app_data={
            "snap_name": snap_name,
            "unix_socket_filepath": socket_path,
        },
    )

    harness.begin_with_initial_hooks()
    charm = harness.charm

    # Verify socket information is available
    assert charm.consul_notify.is_ready
    assert charm.consul_notify.snap_name == snap_name
    assert charm.consul_notify.unix_socket_filepath == socket_path

    # Verify TCP health check is NOT configured despite socket being available
    assert write_config.called
    config = write_config.call_args[0][1]
    config_dict = json.loads(config)
    assert config_dict.get("enable_script_checks") is not True
    assert "services" not in config_dict or len(config_dict.get("services", [])) == 0


def test_tcp_health_check_enabled_by_default(
    harness: Harness[ConsulCharm],
    snap,
    read_config,
    write_config,
    write_tcp_check_script,
    connect_snap_interface,
):
    """Test that TCP health check is enabled by default when socket is available."""
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]
    snap_name = "test-snap"
    socket_path = "data/socket.sock"

    read_config.return_value = {
        "bind_addr": "10.10.0.10",
        "datacenter": datacenter,
        "ports": {
            "dns": -1,
            "http": -1,
            "https": -1,
            "grpc": -1,
            "grpc_tls": -1,
            "serf_lan": 8301,
            "serf_wan": -1,
            "server": 8300,
        },
        "retry_join": [join_server_addresses],
    }

    # Don't set enable-tcp-health-check config, should default to True
    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )

    harness.add_relation(
        "consul-notify",
        "test-app",
        app_data={
            "snap_name": snap_name,
            "unix_socket_filepath": socket_path,
        },
    )

    harness.begin_with_initial_hooks()

    # Verify TCP health check IS configured (default behavior)
    assert write_config.called
    config = write_config.call_args[0][1]
    config_dict = json.loads(config)
    assert config_dict.get("enable_script_checks") is True
    assert "services" in config_dict
    assert len(config_dict["services"]) == 1
    assert config_dict["services"][0]["name"] == "tcp-health-check"


def test_tcp_health_check_disabled_when_socket_not_available(
    harness: Harness[ConsulCharm], snap, read_config, write_config, write_tcp_check_script
):
    """Test that TCP health check is disabled when consul-notify relation is not present."""
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]

    read_config.return_value = {
        "bind_addr": "10.10.0.10",
        "datacenter": datacenter,
        "ports": {
            "dns": -1,
            "http": -1,
            "https": -1,
            "grpc": -1,
            "grpc_tls": -1,
            "serf_lan": 8301,
            "serf_wan": -1,
            "server": 8300,
        },
        "retry_join": [join_server_addresses],
    }

    # Enable TCP health check via config but don't add consul-notify relation
    harness.update_config({"enable-tcp-health-check": True})

    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )

    harness.begin_with_initial_hooks()
    charm = harness.charm

    # Verify socket information is not available
    assert not charm.consul_notify.is_ready

    # Verify TCP health check is NOT configured due to missing socket
    assert write_config.called
    config = write_config.call_args[0][1]
    config_dict = json.loads(config)
    assert config_dict.get("enable_script_checks") is not True
    assert "services" not in config_dict or len(config_dict.get("services", [])) == 0


def test_tcp_health_check_can_be_toggled(
    harness: Harness[ConsulCharm],
    snap,
    read_config,
    write_config,
    write_tcp_check_script,
    connect_snap_interface,
):
    """Test that TCP health check can be enabled and disabled via config changes."""
    datacenter = "test-dc"
    join_server_addresses = ["10.20.0.10:8301"]
    snap_name = "test-snap"
    socket_path = "data/socket.sock"

    read_config.return_value = {
        "bind_addr": "10.10.0.10",
        "datacenter": datacenter,
        "ports": {
            "dns": -1,
            "http": -1,
            "https": -1,
            "grpc": -1,
            "grpc_tls": -1,
            "serf_lan": 8301,
            "serf_wan": -1,
            "server": 8300,
        },
        "retry_join": [join_server_addresses],
    }

    # Start with TCP health check enabled
    harness.update_config({"enable-tcp-health-check": True})

    harness.add_relation(
        "consul-cluster",
        "consul-server",
        app_data={
            "datacenter": datacenter,
            "internal_gossip_endpoints": json.dumps(None),
            "external_gossip_endpoints": json.dumps(join_server_addresses),
            "internal_http_endpoint": json.dumps(None),
            "external_http_endpoint": json.dumps(None),
        },
    )

    harness.add_relation(
        "consul-notify",
        "test-app",
        app_data={
            "snap_name": snap_name,
            "unix_socket_filepath": socket_path,
        },
    )

    harness.begin_with_initial_hooks()

    # Verify TCP health check is enabled
    assert write_config.called
    config = write_config.call_args[0][1]
    config_dict = json.loads(config)
    assert config_dict.get("enable_script_checks") is True
    assert "services" in config_dict

    # Reset mock and disable TCP health check
    write_config.reset_mock()
    harness.update_config({"enable-tcp-health-check": False})

    # Verify TCP health check is now disabled
    assert write_config.called
    config = write_config.call_args[0][1]
    config_dict = json.loads(config)
    assert config_dict.get("enable_script_checks") is not True
    assert "services" not in config_dict or len(config_dict.get("services", [])) == 0

    # Reset mock and re-enable TCP health check
    write_config.reset_mock()
    harness.update_config({"enable-tcp-health-check": True})

    # Verify TCP health check is enabled again
    assert write_config.called
    config = write_config.call_args[0][1]
    config_dict = json.loads(config)
    assert config_dict.get("enable_script_checks") is True
    assert "services" in config_dict
