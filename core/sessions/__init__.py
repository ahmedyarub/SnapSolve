"""Session persistence, split by concern.

* :mod:`core.sessions.store` - paths, legacy migration, locked read-modify-write.
* :mod:`core.sessions.timeline` - chronological view of a session.
* :mod:`core.sessions.index` - background embedding index for search.

:class:`core.session_manager.SessionManager` owns the *current* session on top
of these.
"""
