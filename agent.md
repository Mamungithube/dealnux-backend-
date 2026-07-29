Operations to perform:
  Apply all migrations: account, admin, api_integration, auth, blog, career, contenttypes, custom_ads, homepage, notifications, pages, payment, policy, sessions, store
Running migrations:
  Applying account.0022_alter_sitesettings_referral_reward_amount...Traceback (most recent call last):
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/utils.py", line 103, in _execute
    return self.cursor.execute(sql)
           ^^^^^^^^^^^^^^^^^^^^^^^^
psycopg2.errors.InvalidParameterValue: NUMERIC precision 100000000 must be between 1 and 1000


The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/app/manage.py", line 22, in <module>
    main()
  File "/app/manage.py", line 18, in main
    execute_from_command_line(sys.argv)
  File "/usr/local/lib/python3.12/site-packages/django/core/management/__init__.py", line 442, in execute_from_command_line
    utility.execute()
  File "/usr/local/lib/python3.12/site-packages/django/core/management/__init__.py", line 436, in execute
    self.fetch_command(subcommand).run_from_argv(self.argv)
  File "/usr/local/lib/python3.12/site-packages/django/core/management/base.py", line 420, in run_from_argv
    self.execute(*args, **cmd_options)
  File "/usr/local/lib/python3.12/site-packages/django/core/management/base.py", line 464, in execute
    output = self.handle(*args, **options)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/core/management/base.py", line 111, in wrapper
    res = handle_func(*args, **kwargs)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/core/management/commands/migrate.py", line 353, in handle
    post_migrate_state = executor.migrate(
                         ^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/db/migrations/executor.py", line 135, in migrate
    state = self._migrate_all_forwards(
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/db/migrations/executor.py", line 167, in _migrate_all_forwards
    state = self.apply_migration(
            ^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/db/migrations/executor.py", line 255, in apply_migration
    state = migration.apply(state, schema_editor)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/db/migrations/migration.py", line 132, in apply
    operation.database_forwards(
  File "/usr/local/lib/python3.12/site-packages/django/db/migrations/operations/fields.py", line 241, in database_forwards
    schema_editor.alter_field(from_model, from_field, to_field)
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/base/schema.py", line 912, in alter_field
    self._alter_field(
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/postgresql/schema.py", line 274, in _alter_field
    super()._alter_field(
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/base/schema.py", line 1165, in _alter_field
    self.execute(
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/postgresql/schema.py", line 48, in execute
    return super().execute(sql, None)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/base/schema.py", line 204, in execute
    cursor.execute(sql, params)
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/utils.py", line 122, in execute
    return super().execute(sql, params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/utils.py", line 79, in execute
    return self._execute_with_wrappers(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/utils.py", line 92, in _execute_with_wrappers
    return executor(sql, params, many, context)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/utils.py", line 100, in _execute
    with self.db.wrap_database_errors:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/django/db/utils.py", line 91, in __exit__
    raise dj_exc_value.with_traceback(traceback) from exc_value
  File "/usr/local/lib/python3.12/site-packages/django/db/backends/utils.py", line 103, in _execute
    return self.cursor.execute(sql)
           ^^^^^^^^^^^^^^^^^^^^^^^^
django.db.utils.DataError: NUMERIC precision 100000000 must be between 1 and 1000

[+] Building 17.7s (15/15) FINISHED
 => [internal] load local bake definitions                                                                                                                                                                  0.0s
 => => reading from stdin 554B                                                                                                                                                                              0.0s
 => [internal] load build definition from Dockerfile                                                                                                                                                        0.0s
 => => transferring dockerfile: 482B                                                                                                                                                                        0.0s
 => [internal] load metadata for docker.io/library/python:3.12-slim                                                                                                                                         0.3s
 => [internal] load .dockerignore                                                                                                                                                                           0.0s
 => => transferring context: 2B                                                                                                                                                                             0.0s
 => ERROR importing cache manifest from dealnux-backend                                                                                                                                                     0.1s
 => [stage-0 1/7] FROM docker.io/library/python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de                                                                           0.0s
 => => resolve docker.io/library/python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de                                                                                   0.0s
 => [internal] load build context 