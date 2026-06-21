# Connection-reset / broken-pipe on large uploads (transport)

A network/transport case. Large multipart PUTs are reset mid-transfer
("Connection reset by peer" / "broken pipe") while small PUTs and all downloads
succeed, right after a new firewall/NAT appliance entered the path — the classic
signature of an idle-timeout / MTU / connection-tracking limit on a middlebox, not
an auth or storage problem.

Expected routing: storageops-network-endpoint-access (transport signal). Expected
diagnosis: a path/middlebox transport issue (idle timeout, MTU/MSS clamping, or
NAT conntrack limit) cutting long-lived large-upload connections. Confirms the
v0.6.7 "transport" routing signal (connection reset / broken pipe / RequestTimeout)
routes correctly.
