"""Partners module — gated investor/partner presentation access.

Admins mint shareable access tokens in the admin panel ("Partnerzy" tab)
and send them to investors. Investors open /prezentacja, enter the token,
and the backend verifies it (rate-limited, view-counted) before serving
the presentation HTML. The deck itself never lives in public assets.
"""
