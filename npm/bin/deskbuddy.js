#!/usr/bin/env node
'use strict';

require('../lib/launcher')
  .main()
  .then((code) => {
    process.exitCode = code;
  });
