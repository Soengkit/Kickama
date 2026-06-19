import copy
import json
import unittest

from tools import config_generator


class ConfigGeneratorTests(unittest.TestCase):
    def test_generate_config_applies_development_overrides(self):
        config = config_generator.generate_config("development")

        self.assertEqual(config["app"]["environment"], "development")
        self.assertTrue(config["app"]["debug"])
        self.assertEqual(config["database"]["name"], "tent_dev")
        self.assertEqual(config["market"]["rate_limit_per_second"], 1000)
        self.assertEqual(config["auth"]["jwt_expiry_minutes"], 1440)

    def test_generate_config_applies_staging_overrides(self):
        config = config_generator.generate_config("staging")

        self.assertEqual(config["app"]["environment"], "staging")
        self.assertTrue(config["app"]["debug"])
        self.assertEqual(config["database"]["name"], "tent_staging")
        self.assertEqual(config["database"]["pool_max"], 20)
        self.assertEqual(config["monitoring"]["tracing_sample_rate"], 0.5)

    def test_generate_config_applies_production_overrides(self):
        config = config_generator.generate_config("production")

        self.assertEqual(config["app"]["environment"], "production")
        self.assertFalse(config["app"]["debug"])
        self.assertEqual(config["database"]["name"], "tent_production")
        self.assertEqual(config["database"]["pool_min"], 10)
        self.assertTrue(config["auth"]["mfa_required"])
        self.assertTrue(config["features"]["margin_trading"])

    def test_recursive_override_merge_preserves_nested_values(self):
        base = {
            "server": {"host": "0.0.0.0", "port": 8080, "timeouts": {"read": 30, "write": 60}},
            "features": {"streaming": True},
        }
        override = {
            "server": {"timeouts": {"write": 120}},
            "features": {"dark_mode": False},
        }

        merged = config_generator.merge_config(base, override)

        self.assertEqual(merged["server"]["host"], "0.0.0.0")
        self.assertEqual(merged["server"]["port"], 8080)
        self.assertEqual(merged["server"]["timeouts"]["read"], 30)
        self.assertEqual(merged["server"]["timeouts"]["write"], 120)
        self.assertTrue(merged["features"]["streaming"])
        self.assertFalse(merged["features"]["dark_mode"])

    def test_mask_sensitive_redacts_nested_database_redis_and_jwt_secrets(self):
        config = config_generator.generate_config(
            "production",
            {
                "database": {"password": "db-password"},
                "redis": {"password": "redis-password"},
                "auth": {"jwt_secret": "jwt-secret"},
            },
        )

        masked = config_generator.mask_sensitive(config)

        self.assertEqual(masked["database"]["password"], "***REDACTED***")
        self.assertEqual(masked["redis"]["password"], "***REDACTED***")
        self.assertEqual(masked["auth"]["jwt_secret"], "***REDACTED***")
        self.assertEqual(masked["database"]["name"], "tent_production")
        self.assertEqual(masked["auth"]["jwt_expiry_minutes"], 60)

    def test_sensitive_key_list_is_deduplicated_without_losing_coverage(self):
        self.assertEqual(len(config_generator.SENSITIVE_KEYS), len(set(config_generator.SENSITIVE_KEYS)))
        self.assertIn("database.password", config_generator.SENSITIVE_KEYS)
        self.assertIn("redis.password", config_generator.SENSITIVE_KEYS)
        self.assertIn("auth.jwt_secret", config_generator.SENSITIVE_KEYS)

    def test_json_and_environment_rendering_still_use_masked_config_shape(self):
        config = config_generator.generate_config(
            "development",
            {"database": {"password": "db-password"}, "auth": {"jwt_secret": "jwt-secret"}},
        )
        masked = config_generator.mask_sensitive(copy.deepcopy(config))

        rendered_json = json.loads(config_generator.to_json(masked))
        rendered_env = config_generator.to_dotenv(masked)

        self.assertEqual(rendered_json["database"]["password"], "***REDACTED***")
        self.assertIn("DATABASE_PASSWORD=***REDACTED***", rendered_env)
        self.assertIn("AUTH_JWT_SECRET=***REDACTED***", rendered_env)


if __name__ == "__main__":
    unittest.main()
