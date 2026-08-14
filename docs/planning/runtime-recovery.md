# Runtime recovery baseline

The cumulative runtime line starts from Git commit
`6b8d3626445bd577cc6c5af80f3b84e30e2c7712`.

That commit preserves the Milestone 1 repository/API foundation and the Milestone 7
Boundary Contract Conformance and Assurance Suite. It does not contain the unavailable
Milestone 2–6 production runtime. The PostgreSQL store and SQLAlchemy unit of work at
that point are intentional fail-closed stubs.

Runtime implementation after the baseline is ordinary new development. Release notes
must distinguish production paths, reference-only paths, and planned paths, and must
never imply that unavailable history was reconstructed.

An advertised runtime capability is complete only when a real implementation adapter
passes its Boundary Contract profile against supported infrastructure.
