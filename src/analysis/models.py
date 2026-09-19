"""Data models for the SecurePacket Analyzer Pro analysis pipeline.

Defines all data structures used by capture, analysis, and dashboard
engines. Every model supports thread-safe updates where noted, full
serialization via ``to_dict`` / ``from_dict``, and comprehensive type
hints.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PacketDirection(Enum):
    """Logical direction of a packet relative to the capture point."""

    UNKNOWN = auto()
    INBOUND = auto()
    OUTBOUND = auto()
    LOCAL = auto()
    EXTERNAL = auto()
    BIDIRECTIONAL = auto()


class HostType(Enum):
    """Classifier for the role of a host on the network."""

    UNKNOWN = auto()
    ROUTER = auto()
    SWITCH = auto()
    SERVER = auto()
    WORKSTATION = auto()
    MOBILE = auto()
    IOT = auto()
    PRINTER = auto()
    VIRTUAL = auto()
    CONTAINER = auto()
    GATEWAY = auto()


class ConnectionState(Enum):
    """TCP / connection-oriented state machine values."""

    UNKNOWN = auto()
    ACTIVE = auto()
    IDLE = auto()
    CLOSED = auto()
    LISTENING = auto()
    SYN_SENT = auto()
    SYN_RECEIVED = auto()
    ESTABLISHED = auto()
    FIN_WAIT = auto()
    TIME_WAIT = auto()
    CLOSING = auto()


class ProtocolCategory(Enum):
    """High-level classification of network protocols."""

    UNKNOWN = auto()
    LINK = auto()
    NETWORK = auto()
    TRANSPORT = auto()
    APPLICATION = auto()
    MANAGEMENT = auto()
    SECURITY = auto()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _float_to_iso(ts: float) -> str:
    """Convert an epoch float to an ISO-8601 string."""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# PacketInfo
# ---------------------------------------------------------------------------


@dataclass
class PacketInfo:
    """Fundamental unit passed from capture through every analysis pipeline.

    Instances are created by the capture layer and consumed (read-only) by
    all downstream analyzers.  Mutability is intentionally kept to a minimum;
    downstream engines should never modify a ``PacketInfo`` once created.
    """

    packet_number: int
    timestamp: float
    capture_interface: str
    frame_length: int

    source_mac: str = ""
    destination_mac: str = ""
    source_ip: str = ""
    destination_ip: str = ""
    source_port: int = 0
    destination_port: int = 0
    protocol: str = ""
    transport_protocol: str = ""
    application_protocol: str = ""
    ip_version: int = 0
    ttl: int = 0
    tcp_flags: str = ""
    tcp_sequence: int = 0
    tcp_ack: int = 0
    tcp_window: int = 0
    udp_length: int = 0
    icmp_type: int = 0
    icmp_code: int = 0
    vlan_id: int = 0
    is_fragmented: bool = False
    is_malformed: bool = False
    payload_length: int = 0

    # Application-layer hints
    dns_query: str = ""
    http_method: str = ""
    http_host: str = ""
    http_uri: str = ""
    tls_version: str = ""

    raw_bytes: bytes = b""
    direction: PacketDirection = PacketDirection.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the packet to a JSON-safe dictionary."""
        return {
            "packet_number": self.packet_number,
            "timestamp": self.timestamp,
            "capture_interface": self.capture_interface,
            "frame_length": self.frame_length,
            "source_mac": self.source_mac,
            "destination_mac": self.destination_mac,
            "source_ip": self.source_ip,
            "destination_ip": self.destination_ip,
            "source_port": self.source_port,
            "destination_port": self.destination_port,
            "protocol": self.protocol,
            "transport_protocol": self.transport_protocol,
            "application_protocol": self.application_protocol,
            "ip_version": self.ip_version,
            "ttl": self.ttl,
            "tcp_flags": self.tcp_flags,
            "tcp_sequence": self.tcp_sequence,
            "tcp_ack": self.tcp_ack,
            "tcp_window": self.tcp_window,
            "udp_length": self.udp_length,
            "icmp_type": self.icmp_type,
            "icmp_code": self.icmp_code,
            "vlan_id": self.vlan_id,
            "is_fragmented": self.is_fragmented,
            "is_malformed": self.is_malformed,
            "payload_length": self.payload_length,
            "dns_query": self.dns_query,
            "http_method": self.http_method,
            "http_host": self.http_host,
            "http_uri": self.http_uri,
            "tls_version": self.tls_version,
            "direction": self.direction.name,
            "metadata": self.metadata,
        }

    # -- convenience accessors -----------------------------------------------

    def source_endpoint(self) -> str:
        """Return ``ip:port`` or just ``ip`` when no port is present."""
        if self.source_port:
            return f"{self.source_ip}:{self.source_port}"
        return self.source_ip

    def destination_endpoint(self) -> str:
        """Return ``ip:port`` or just ``ip`` when no port is present."""
        if self.destination_port:
            return f"{self.destination_ip}:{self.destination_port}"
        return self.destination_ip

    def is_tcp(self) -> bool:
        """Return *True* if the packet uses TCP."""
        return self.transport_protocol.upper() == "TCP" or self.protocol.upper() == "TCP"

    def is_udp(self) -> bool:
        """Return *True* if the packet uses UDP."""
        return self.transport_protocol.upper() == "UDP" or self.protocol.upper() == "UDP"

    def is_icmp(self) -> bool:
        """Return *True* if the packet uses ICMP."""
        return self.protocol.upper() == "ICMP"

    def is_ipv6(self) -> bool:
        """Return *True* if the packet is IPv6."""
        return self.ip_version == 6


# ---------------------------------------------------------------------------
# HostInfo
# ---------------------------------------------------------------------------


@dataclass
class HostInfo:
    """Aggregated statistics for a single network host.

    All mutable fields are updated via :meth:`update_from_packet` which is
    protected by an internal lock so that multiple capture threads may
    safely update the same ``HostInfo`` concurrently.
    """

    ip_address: str
    mac_address: str = ""
    hostname: str = ""
    vendor: str = ""
    host_type: HostType = HostType.UNKNOWN
    first_seen: str = ""
    last_seen: str = ""
    packets_sent: int = 0
    packets_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    protocols_used: set[str] = field(default_factory=set)
    open_ports: set[int] = field(default_factory=set)
    dns_names: list[str] = field(default_factory=list)
    connection_count: int = 0
    interfaces: set[str] = field(default_factory=set)
    is_favorited: bool = False
    notes: str = ""
    bookmarks: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update_from_packet(self, packet: PacketInfo, is_outgoing: bool) -> None:
        """Thread-safe update of host statistics from a single packet.

        Parameters
        ----------
        packet:
            The captured packet to incorporate.
        is_outgoing:
            *True* when the packet originated from this host.
        """
        with self._lock:
            now_iso = datetime.fromtimestamp(packet.timestamp, tz=UTC).isoformat()

            if not self.first_seen:
                self.first_seen = now_iso
            self.last_seen = now_iso

            if is_outgoing:
                self.packets_sent += 1
                self.bytes_sent += packet.frame_length
            else:
                self.packets_received += 1
                self.bytes_received += packet.frame_length

            if packet.protocol:
                self.protocols_used.add(packet.protocol)
            if packet.transport_protocol:
                self.protocols_used.add(packet.transport_protocol)

            if is_outgoing and packet.destination_port:
                self.open_ports.add(packet.destination_port)
            elif not is_outgoing and packet.source_port:
                self.open_ports.add(packet.source_port)

            if packet.capture_interface:
                self.interfaces.add(packet.capture_interface)

            if packet.dns_query and packet.dns_query not in self.dns_names:
                self.dns_names.append(packet.dns_query)

    def is_active(self, recent_seconds: float = 300.0) -> bool:
        """Return *True* if the host was seen within *recent_seconds*."""
        if not self.last_seen:
            return False
        try:
            last = datetime.fromisoformat(self.last_seen)
            now = datetime.now(UTC)
            delta = (now - last).total_seconds()
            return delta <= recent_seconds
        except ValueError:
            return False

    def total_bytes(self) -> int:
        """Total bytes sent and received by this host."""
        return self.bytes_sent + self.bytes_received

    def total_packets(self) -> int:
        """Total packets sent and received by this host."""
        return self.packets_sent + self.packets_received

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "hostname": self.hostname,
            "vendor": self.vendor,
            "host_type": self.host_type.name,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "protocols_used": sorted(self.protocols_used),
            "open_ports": sorted(self.open_ports),
            "dns_names": self.dns_names,
            "connection_count": self.connection_count,
            "interfaces": sorted(self.interfaces),
            "is_favorited": self.is_favorited,
            "notes": self.notes,
            "bookmarks": self.bookmarks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HostInfo:
        """Reconstruct a ``HostInfo`` from a previously serialized dict."""
        host = cls(ip_address=data["ip_address"])
        host.mac_address = data.get("mac_address", "")
        host.hostname = data.get("hostname", "")
        host.vendor = data.get("vendor", "")
        host.host_type = HostType[data.get("host_type", "UNKNOWN")]
        host.first_seen = data.get("first_seen", "")
        host.last_seen = data.get("last_seen", "")
        host.packets_sent = data.get("packets_sent", 0)
        host.packets_received = data.get("packets_received", 0)
        host.bytes_sent = data.get("bytes_sent", 0)
        host.bytes_received = data.get("bytes_received", 0)
        host.protocols_used = set(data.get("protocols_used", []))
        host.open_ports = set(data.get("open_ports", []))
        host.dns_names = data.get("dns_names", [])
        host.connection_count = data.get("connection_count", 0)
        host.interfaces = set(data.get("interfaces", []))
        host.is_favorited = data.get("is_favorited", False)
        host.notes = data.get("notes", "")
        host.bookmarks = data.get("bookmarks", [])
        return host


# ---------------------------------------------------------------------------
# ConnectionInfo
# ---------------------------------------------------------------------------


@dataclass
class ConnectionInfo:
    """Represents a single unidirectional or bidirectional connection.

    Identified by the 5-tuple ``(protocol, src_ip, src_port, dst_ip, dst_port)``.
    Thread-safe via an internal lock for concurrent capture scenarios.
    """

    connection_id: str
    source_ip: str
    destination_ip: str
    source_port: int
    destination_port: int
    protocol: str

    state: ConnectionState = ConnectionState.UNKNOWN
    start_time: str = ""
    last_activity: str = ""
    duration: float = 0.0
    packets: int = 0
    bytes_transferred: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    average_packet_size: float = 0.0
    direction: PacketDirection = PacketDirection.UNKNOWN
    flags: list[str] = field(default_factory=list)
    is_favorited: bool = False
    notes: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update_from_packet(self, packet: PacketInfo) -> None:
        """Thread-safe update from a single packet."""
        with self._lock:
            now_iso = datetime.fromtimestamp(packet.timestamp, tz=UTC).isoformat()

            if not self.start_time:
                self.start_time = now_iso
            self.last_activity = now_iso

            self.packets += 1
            self.bytes_transferred += packet.frame_length

            if packet.source_ip == self.source_ip:
                self.bytes_sent += packet.frame_length
            else:
                self.bytes_received += packet.frame_length

            self.average_packet_size = (
                self.bytes_transferred / self.packets if self.packets else 0.0
            )

            if packet.is_tcp() and packet.tcp_flags:
                for flag in packet.tcp_flags.split(","):
                    flag = flag.strip()
                    if flag and flag not in self.flags:
                        self.flags.append(flag)

            if self.start_time and self.last_activity:
                try:
                    t0 = datetime.fromisoformat(self.start_time)
                    t1 = datetime.fromisoformat(self.last_activity)
                    self.duration = (t1 - t0).total_seconds()
                except ValueError:
                    pass

    def is_active(self, timeout: float = 300.0) -> bool:
        """Return *True* if the connection had activity within *timeout* seconds."""
        if not self.last_activity:
            return False
        try:
            last = datetime.fromisoformat(self.last_activity)
            now = datetime.now(UTC)
            return (now - last).total_seconds() <= timeout
        except ValueError:
            return False

    def key(self) -> str:
        """Canonical 5-tuple key: ``proto:sip:sport:dip:dport``."""
        return f"{self.protocol}:{self.source_ip}:{self.source_port}:{self.destination_ip}:{self.destination_port}"

    def reverse_key(self) -> str:
        """The reversed-direction key used to match reply packets."""
        return f"{self.protocol}:{self.destination_ip}:{self.destination_port}:{self.source_ip}:{self.source_port}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "connection_id": self.connection_id,
            "source_ip": self.source_ip,
            "destination_ip": self.destination_ip,
            "source_port": self.source_port,
            "destination_port": self.destination_port,
            "protocol": self.protocol,
            "state": self.state.name,
            "start_time": self.start_time,
            "last_activity": self.last_activity,
            "duration": self.duration,
            "packets": self.packets,
            "bytes_transferred": self.bytes_transferred,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "average_packet_size": self.average_packet_size,
            "direction": self.direction.name,
            "flags": self.flags,
            "is_favorited": self.is_favorited,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectionInfo:
        """Reconstruct a ``ConnectionInfo`` from a serialized dict."""
        conn = cls(
            connection_id=data["connection_id"],
            source_ip=data["source_ip"],
            destination_ip=data["destination_ip"],
            source_port=data["source_port"],
            destination_port=data["destination_port"],
            protocol=data["protocol"],
        )
        conn.state = ConnectionState[data.get("state", "UNKNOWN")]
        conn.start_time = data.get("start_time", "")
        conn.last_activity = data.get("last_activity", "")
        conn.duration = data.get("duration", 0.0)
        conn.packets = data.get("packets", 0)
        conn.bytes_transferred = data.get("bytes_transferred", 0)
        conn.bytes_sent = data.get("bytes_sent", 0)
        conn.bytes_received = data.get("bytes_received", 0)
        conn.average_packet_size = data.get("average_packet_size", 0.0)
        conn.direction = PacketDirection[data.get("direction", "UNKNOWN")]
        conn.flags = data.get("flags", [])
        conn.is_favorited = data.get("is_favorited", False)
        conn.notes = data.get("notes", "")
        return conn


# ---------------------------------------------------------------------------
# ProtocolStats
# ---------------------------------------------------------------------------


@dataclass
class ProtocolStats:
    """Per-protocol aggregated statistics.

    Supports nested sub-protocols (e.g., ``HTTP > GET``, ``TLS > 1.3``).
    All updates are thread-safe.
    """

    protocol_name: str
    category: ProtocolCategory = ProtocolCategory.UNKNOWN
    packet_count: int = 0
    byte_count: int = 0
    percentage: float = 0.0
    bandwidth_bps: float = 0.0
    average_size: float = 0.0
    peak_rate: float = 0.0
    error_count: int = 0
    malformed_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    sub_protocols: dict[str, ProtocolStats] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update_from_packet(self, packet: PacketInfo, length: int) -> None:
        """Thread-safe update from a single packet.

        Parameters
        ----------
        packet:
            The captured packet.
        length:
            The wire-length of the packet in bytes.
        """
        with self._lock:
            now_iso = datetime.fromtimestamp(packet.timestamp, tz=UTC).isoformat()

            if not self.first_seen:
                self.first_seen = now_iso
            self.last_seen = now_iso

            self.packet_count += 1
            self.byte_count += length
            self.average_size = self.byte_count / self.packet_count

            if packet.is_malformed:
                self.malformed_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary, including sub-protocols."""
        return {
            "protocol_name": self.protocol_name,
            "category": self.category.name,
            "packet_count": self.packet_count,
            "byte_count": self.byte_count,
            "percentage": self.percentage,
            "bandwidth_bps": self.bandwidth_bps,
            "average_size": self.average_size,
            "peak_rate": self.peak_rate,
            "error_count": self.error_count,
            "malformed_count": self.malformed_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "sub_protocols": {name: sub.to_dict() for name, sub in self.sub_protocols.items()},
        }


# ---------------------------------------------------------------------------
# BandwidthSample
# ---------------------------------------------------------------------------


@dataclass
class BandwidthSample:
    """A single point-in-time bandwidth measurement.

    Typically collected at regular intervals to build a time-series for
    the dashboard.
    """

    timestamp: float
    bytes_in: int = 0
    bytes_out: int = 0
    packets_in: int = 0
    packets_out: int = 0
    bits_per_second: float = 0.0

    def total_bytes(self) -> int:
        """Total bytes for this sample (inbound + outbound)."""
        return self.bytes_in + self.bytes_out

    def total_packets(self) -> int:
        """Total packets for this sample (inbound + outbound)."""
        return self.packets_in + self.packets_out


# ---------------------------------------------------------------------------
# TimelineEvent
# ---------------------------------------------------------------------------


@dataclass
class TimelineEvent:
    """A single event on the analysis timeline.

    Used to track notable occurrences such as connection starts, anomalies,
    or protocol errors.
    """

    timestamp: float
    event_type: str
    description: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ConversationInfo
# ---------------------------------------------------------------------------


@dataclass
class ConversationInfo:
    """A bidirectional conversation between two hosts.

    Direction-aware counting is performed by :meth:`update_from_packet`
    which is protected by an internal lock.
    """

    conversation_id: str
    host_a: str
    host_b: str
    protocol: str
    port_a: int = 0
    port_b: int = 0
    packets_a_to_b: int = 0
    packets_b_to_a: int = 0
    bytes_a_to_b: int = 0
    bytes_b_to_a: int = 0
    start_time: str = ""
    last_activity: str = ""
    duration: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update_from_packet(self, packet: PacketInfo) -> None:
        """Thread-safe, direction-aware update from a single packet."""
        with self._lock:
            now_iso = datetime.fromtimestamp(packet.timestamp, tz=UTC).isoformat()

            if not self.start_time:
                self.start_time = now_iso
            self.last_activity = now_iso

            src = packet.source_ip
            if src == self.host_a:
                self.packets_a_to_b += 1
                self.bytes_a_to_b += packet.frame_length
            else:
                self.packets_b_to_a += 1
                self.bytes_b_to_a += packet.frame_length

            if self.start_time and self.last_activity:
                try:
                    t0 = datetime.fromisoformat(self.start_time)
                    t1 = datetime.fromisoformat(self.last_activity)
                    self.duration = (t1 - t0).total_seconds()
                except ValueError:
                    pass

    def total_packets(self) -> int:
        """Total packets exchanged in this conversation."""
        return self.packets_a_to_b + self.packets_b_to_a

    def total_bytes(self) -> int:
        """Total bytes exchanged in this conversation."""
        return self.bytes_a_to_b + self.bytes_b_to_a

    def key(self) -> str:
        """Canonical key: ``ipa:ipb:proto`` with lexicographic ordering."""
        if self.host_a <= self.host_b:
            return f"{self.host_a}:{self.host_b}:{self.protocol}"
        return f"{self.host_b}:{self.host_a}:{self.protocol}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "conversation_id": self.conversation_id,
            "host_a": self.host_a,
            "host_b": self.host_b,
            "protocol": self.protocol,
            "port_a": self.port_a,
            "port_b": self.port_b,
            "packets_a_to_b": self.packets_a_to_b,
            "packets_b_to_a": self.packets_b_to_a,
            "bytes_a_to_b": self.bytes_a_to_b,
            "bytes_b_to_a": self.bytes_b_to_a,
            "start_time": self.start_time,
            "last_activity": self.last_activity,
            "duration": self.duration,
        }


# ---------------------------------------------------------------------------
# SessionInfo
# ---------------------------------------------------------------------------


@dataclass
class SessionInfo:
    """Represents a higher-level session over one or more connections.

    Sessions track activity and expiration for UI grouping and cleanup.
    """

    session_id: str
    connection_id: str
    start_time: str
    end_time: str = ""
    duration: float = 0.0
    packets: int = 0
    bytes_transferred: int = 0
    protocols: list[str] = field(default_factory=list)
    state: ConnectionState = ConnectionState.ACTIVE
    timeout: float = 300.0

    def is_expired(self) -> bool:
        """Return *True* if the session has exceeded its idle timeout."""
        if self.state in (ConnectionState.CLOSED, ConnectionState.CLOSING):
            return True
        if not self.start_time:
            return True
        try:
            if self.end_time:
                ref = datetime.fromisoformat(self.end_time)
            else:
                ref = datetime.now(UTC)
            start = datetime.fromisoformat(self.start_time)
            elapsed = (ref - start).total_seconds()
            if self.packets == 0 and elapsed > self.timeout:
                return True
            return False
        except ValueError:
            return True

    def update_activity(self) -> None:
        """Reset the session activity timestamp and increment counters."""
        self.start_time = _now_iso()
        self.duration = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "session_id": self.session_id,
            "connection_id": self.connection_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "packets": self.packets,
            "bytes_transferred": self.bytes_transferred,
            "protocols": self.protocols,
            "state": self.state.name,
            "timeout": self.timeout,
        }


# ---------------------------------------------------------------------------
# TrafficSnapshot
# ---------------------------------------------------------------------------


@dataclass
class TrafficSnapshot:
    """A point-in-time snapshot of all analytics for the dashboard.

    Generated periodically by the analysis engine and consumed by the
    UI layer.  All fields are plain values (no locks) because snapshots
    are replaced wholesale rather than mutated.
    """

    timestamp: float
    total_packets: int = 0
    total_bytes: int = 0
    packets_per_second: float = 0.0
    bytes_per_second: float = 0.0
    peak_pps: float = 0.0
    peak_bps: float = 0.0
    active_hosts: int = 0
    active_connections: int = 0
    protocols_seen: int = 0
    capture_duration: float = 0.0
    average_packet_size: float = 0.0
    largest_packet: int = 0
    smallest_packet: int = 999999
    dropped_packets: int = 0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    cache_size: int = 0
    top_protocols: list[tuple[str, int]] = field(default_factory=list)
    top_source_ips: list[tuple[str, int]] = field(default_factory=list)
    top_destination_ips: list[tuple[str, int]] = field(default_factory=list)
    top_source_ports: list[tuple[int, int]] = field(default_factory=list)
    top_destination_ports: list[tuple[int, int]] = field(default_factory=list)
    top_conversations: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "timestamp": self.timestamp,
            "total_packets": self.total_packets,
            "total_bytes": self.total_bytes,
            "packets_per_second": self.packets_per_second,
            "bytes_per_second": self.bytes_per_second,
            "peak_pps": self.peak_pps,
            "peak_bps": self.peak_bps,
            "active_hosts": self.active_hosts,
            "active_connections": self.active_connections,
            "protocols_seen": self.protocols_seen,
            "capture_duration": self.capture_duration,
            "average_packet_size": self.average_packet_size,
            "largest_packet": self.largest_packet,
            "smallest_packet": self.smallest_packet,
            "dropped_packets": self.dropped_packets,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "cache_size": self.cache_size,
            "top_protocols": self.top_protocols,
            "top_source_ips": self.top_source_ips,
            "top_destination_ips": self.top_destination_ips,
            "top_source_ports": self.top_source_ports,
            "top_destination_ports": self.top_destination_ports,
            "top_conversations": self.top_conversations,
        }
