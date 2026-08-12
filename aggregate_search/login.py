# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""
Thin wrapper for login-only worker mode.

The actual implementation lives in ``aggregate_search.worker._run_login``.
This module is kept as a public entry point for the API router.
"""

from aggregate_search.worker import _run_login as run_login  # noqa: F401
