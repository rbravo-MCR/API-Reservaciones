# Tables de la app de reserves

## affiliates

```
CREATE TABLE `affiliates` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `type` enum('OTA','METASEARCH','LOYALTY_PROGRAM','AIRLINE','BANK','OTHER') NOT NULL,
  `website_url` varchar(255) DEFAULT NULL,
  `tracking_code` varchar(100) DEFAULT NULL,
  `contact_email` varchar(255) DEFAULT NULL,
  `contact_phone` varchar(50) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `tracking_code` (`tracking_code`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## app_customers

```
CREATE TABLE `app_customers` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `email_verified_at` timestamp NULL DEFAULT NULL,
  `password_hash` varchar(255) NOT NULL,
  `first_name` varchar(150) NOT NULL,
  `last_name` varchar(150) NOT NULL,
  `phone` varchar(50) DEFAULT NULL,
  `country_id` bigint unsigned DEFAULT NULL,
  `preferred_language` varchar(10) DEFAULT NULL,
  `preferred_currency` char(3) DEFAULT NULL,
  `marketing_opt_in` tinyint(1) NOT NULL DEFAULT '1',
  `status` enum('ACTIVE','INACTIVE','BANNED','PENDING_VERIFICATION') NOT NULL DEFAULT 'ACTIVE',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`),
  KEY `fk_app_customers_country` (`country_id`),
  CONSTRAINT `fk_app_customers_country` FOREIGN KEY (`country_id`) REFERENCES `countries` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

## **blog_post_traslations**

```
CREATE TABLE `blog_post_translations` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `blog_post_id` bigint unsigned NOT NULL,
  `locale` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subtitle` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `excerpt` text COLLATE utf8mb4_unicode_ci,
  `body` longtext COLLATE utf8mb4_unicode_ci,
  `seo_title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `seo_description` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```



## blog_posts

CREATE TABLE `blog_posts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `slug` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `category` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('draft','published') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `is_featured` tinyint(1) NOT NULL DEFAULT '0',
  `hero_image_url` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `published_at` timestamp NULL DEFAULT NULL,
  `author_name` varchar(150) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `blog_posts_slug_unique` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

## **car_categories**

`CREATE TABLE `car_categories` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `acriss_code` varchar(10) NOT NULL,
  `code` varchar(50) DEFAULT NULL,
  `name` varchar(150) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `doors` tinyint unsigned DEFAULT NULL,
  `seats` tinyint unsigned DEFAULT NULL,
  `luggage_small` tinyint unsigned DEFAULT NULL,
  `luggage_large` tinyint unsigned DEFAULT NULL,
  `transmission` enum('MANUAL','AUTOMATIC','OTHER') DEFAULT NULL,
  `air_conditioning` tinyint(1) NOT NULL DEFAULT '1',
  `example_models` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `acriss_code` (`acriss_code`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;`

## **cities**

```
`CREATE TABLE `cities` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `country_id` bigint unsigned NOT NULL,
  `name` varchar(150) NOT NULL,
  `state_name` varchar(150) DEFAULT NULL,
  `iata_code` char(3) DEFAULT NULL,
  `time_zone` varchar(100) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_cities_country` (`country_id`),
  CONSTRAINT `fk_cities_country` FOREIGN KEY (`country_id`) REFERENCES `countries` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;`
```



## **cms_page_translations**

```
` CREATE TABLE `cities` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `country_id` bigint unsigned NOT NULL,
  `name` varchar(150) NOT NULL,
  `state_name` varchar(150) DEFAULT NULL,
  `iata_code` char(3) DEFAULT NULL,
  `time_zone` varchar(100) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_cities_country` (`country_id`),
  CONSTRAINT `fk_cities_country` FOREIGN KEY (`country_id`) REFERENCES `countries` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;`
```



## **cms_pages**

```
`CREATE TABLE `cms_pages` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `slug` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `section` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'legal',
  `is_published` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `cms_pages_slug_unique` (`slug`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;`
```



## corporate_account_users

```
CREATE TABLE `corporate_account_users` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `corporate_account_id` bigint unsigned NOT NULL,
  `crm_user_id` bigint unsigned NOT NULL,
  `role` enum('OWNER','ACCOUNT_MANAGER','SUPPORT') NOT NULL DEFAULT 'ACCOUNT_MANAGER',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_corporate_account_users_account` (`corporate_account_id`),
  KEY `fk_corporate_account_users_crm_user` (`crm_user_id`),
  CONSTRAINT `fk_corporate_account_users_account` FOREIGN KEY (`corporate_account_id`) REFERENCES `corporate_accounts` (`id`),
  CONSTRAINT `fk_corporate_account_users_crm_user` FOREIGN KEY (`crm_user_id`) REFERENCES `crm_users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
```

## **corporate_accounts**

CREATE TABLE `corporate_accounts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `type` enum('TRAVEL_AGENCY','CORPORATE','WHOLESALER','AFFILIATE','OTHER') NOT NULL,
  `country_id` bigint unsigned DEFAULT NULL,
  `website_url` varchar(255) DEFAULT NULL,
  `contact_name` varchar(255) DEFAULT NULL,
  `contact_email` varchar(255) DEFAULT NULL,
  `contact_phone` varchar(50) DEFAULT NULL,
  `credit_limit_amount` decimal(12,2) DEFAULT NULL,
  `payment_terms_days` int DEFAULT NULL,
  `default_commission_pct` decimal(5,2) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_corporate_accounts_country` (`country_id`),
  CONSTRAINT `fk_corporate_accounts_country` FOREIGN KEY (`country_id`) REFERENCES `countries` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;



## **countries**

```
CREATE TABLE `countries` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `iso_code` char(2) NOT NULL,
  `iso3_code` char(3) DEFAULT NULL,
  `name` varchar(150) NOT NULL,
  `default_currency_code` char(3) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `iso_code` (`iso_code`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci; 
```

## **country_car_categories**

```
CREATE TABLE `country_car_categories` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `country_id` bigint unsigned NOT NULL,
  `car_category_id` bigint unsigned NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `default_public_markup_pct` decimal(5,2) DEFAULT NULL,
  `default_supplier_cost_pct` decimal(5,2) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_country_car_category` (`country_id`,`car_category_id`),
  KEY `fk_country_car_categories_category` (`car_category_id`),
  CONSTRAINT `fk_country_car_categories_category` FOREIGN KEY (`car_category_id`) REFERENCES `car_categories` (`id`),
  CONSTRAINT `fk_country_car_categories_country` FOREIGN KEY (`country_id`) REFERENCES `countries` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

## **crm_roles**

```
CREATE TABLE `crm_roles` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(50) NOT NULL,
  `name` varchar(150) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

## **crm_users**

```
CREATE TABLE `crm_users` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `first_name` varchar(150) NOT NULL,
  `last_name` varchar(150) NOT NULL,
  `role_id` bigint unsigned NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `time_zone` varchar(100) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`),
  KEY `fk_crm_users_role` (`role_id`),
  CONSTRAINT `fk_crm_users_role` FOREIGN KEY (`role_id`) REFERENCES `crm_roles` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

## **discounts**

```
CREATE TABLE `discounts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(50) NOT NULL,
  `name` varchar(255) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `type` enum('PERCENT','FIXED_AMOUNT','CASHBACK') NOT NULL,
  `value` decimal(10,2) NOT NULL,
  `max_amount` decimal(12,2) DEFAULT NULL,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `min_rental_days` smallint unsigned DEFAULT NULL,
  `min_public_price_total` decimal(12,2) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

## **idempotency_keys**

```
CREATE TABLE `idempotency_keys` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `scope` varchar(32) NOT NULL,
  `idem_key` varchar(128) NOT NULL,
  `request_hash` char(64) NOT NULL,
  `response_json` json DEFAULT NULL,
  `http_status` smallint DEFAULT NULL,
  `reference_reservation_id` bigint unsigned DEFAULT NULL,
  `reference_customer_id` bigint unsigned DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scope_key` (`scope`,`idem_key`),
  KEY `idx_created` (`created_at`),
  KEY `idx_ttl_cleanup` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

## **offices**

```
CREATE TABLE `offices` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `supplier_id` bigint unsigned NOT NULL,
  `city_id` bigint unsigned NOT NULL,
  `code` varchar(50) NOT NULL,
  `name` varchar(255) NOT NULL,
  `type` enum('AIRPORT','DOWNTOWN','NEIGHBORHOOD','PORT','TRAIN_STATION','OTHER') NOT NULL,
  `iata_code` char(3) DEFAULT NULL,
  `address_line1` varchar(255) DEFAULT NULL,
  `address_line2` varchar(255) DEFAULT NULL,
  `postal_code` varchar(20) DEFAULT NULL,
  `latitude` decimal(10,7) DEFAULT NULL,
  `longitude` decimal(10,7) DEFAULT NULL,
  `opening_hours_json` json DEFAULT NULL,
  `pickup_instructions` text,
  `dropoff_instructions` text,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_offices_supplier_code` (`supplier_id`,`code`),
  KEY `fk_offices_city` (`city_id`),
  KEY `idx_offices_code` (`code`),
  KEY `idx_offices_iata` (`iata_code`),
  KEY `idx_offices_supplier_active` (`supplier_id`,`is_active`),
  CONSTRAINT `fk_offices_city` FOREIGN KEY (`city_id`) REFERENCES `cities` (`id`),
  CONSTRAINT `fk_offices_supplier` FOREIGN KEY (`supplier_id`) REFERENCES `suppliers` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

## **outbox_events**

```
CREATE TABLE `outbox_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_type` varchar(64) NOT NULL,
  `aggregate_type` varchar(32) NOT NULL,
  `aggregate_id` bigint unsigned NOT NULL,
  `payload` json NOT NULL,
  `status` varchar(16) NOT NULL DEFAULT 'NEW',
  `attempts` int NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `locked_by` varchar(64) DEFAULT NULL,
  `locked_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  `lock_expires_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_status_next` (`status`,`next_attempt_at`),
  KEY `idx_aggregate` (`aggregate_type`,`aggregate_id`),
  KEY `idx_outbox_worker_claim` (`status`,`next_attempt_at`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

## **payments**

```
CREATE TABLE `payments` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `provider` varchar(100) NOT NULL,
  `provider_transaction_id` varchar(255) DEFAULT NULL,
  `method` varchar(100) DEFAULT NULL,
  `amount` decimal(12,2) NOT NULL,
  `currency_code` char(3) NOT NULL,
  `status` enum('PENDING','AUTHORIZED','CAPTURED','FAILED','REFUNDED','PARTIALLY_REFUNDED','CHARGEBACK') NOT NULL DEFAULT 'PENDING',
  `captured_at` datetime DEFAULT NULL,
  `refunded_at` datetime DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `stripe_payment_intent_id` varchar(64) DEFAULT NULL,
  `stripe_charge_id` varchar(64) DEFAULT NULL,
  `stripe_event_id` varchar(64) DEFAULT NULL,
  `amount_refunded` decimal(12,2) NOT NULL DEFAULT '0.00',
  `fee_amount` decimal(12,2) DEFAULT NULL,
  `net_amount` decimal(12,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payments_provider_tx` (`provider`,`provider_transaction_id`),
  UNIQUE KEY `uq_payments_stripe_event` (`provider`,`stripe_event_id`),
  KEY `idx_payments_status` (`status`),
  KEY `idx_payments_reservation` (`reservation_id`),
  KEY `idx_payments_status_created` (`status`,`created_at`),
  KEY `idx_payments_pi` (`stripe_payment_intent_id`),
  KEY `idx_payments_charge` (`stripe_charge_id`),
  KEY `idx_payments_reservation_created` (`reservation_id`,`created_at`),
  CONSTRAINT `fk_payments_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

## **reservation_assignments**

```
CREATE TABLE `reservation_assignments` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `crm_user_id` bigint unsigned NOT NULL,
  `role` enum('OWNER','FOLLOWUP','SUPPORT') NOT NULL DEFAULT 'OWNER',
  `assigned_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `unassigned_at` datetime DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_res_assign_reservation_active` (`reservation_id`,`is_active`),
  KEY `idx_res_assign_crm_user_active` (`crm_user_id`,`is_active`),
  KEY `idx_ra_reservation_active` (`reservation_id`,`is_active`),
  KEY `idx_ra_user_active` (`crm_user_id`,`is_active`),
  CONSTRAINT `fk_res_assign_crm_user` FOREIGN KEY (`crm_user_id`) REFERENCES `crm_users` (`id`),
  CONSTRAINT `fk_res_assign_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_contacts**

```
CREATE TABLE `reservation_contacts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `contact_type` enum('BOOKER','EMERGENCY') NOT NULL DEFAULT 'BOOKER',
  `full_name` varchar(255) NOT NULL,
  `email` varchar(255) NOT NULL,
  `phone` varchar(50) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rc_res_contact_type` (`reservation_id`,`contact_type`),
  KEY `idx_rc_reservation_created` (`reservation_id`,`created_at`),
  KEY `idx_rc_email` (`email`),
  KEY `idx_rc_phone` (`phone`),
  KEY `idx_rc_contact_type` (`contact_type`),
  CONSTRAINT `fk_rc_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`),
  CONSTRAINT `fk_reservation_contacts_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_discounts**

```
CREATE TABLE `reservation_discounts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `discount_id` bigint unsigned DEFAULT NULL,
  `source` enum('COUPON','CAMPAIGN','LOYALTY','MANUAL') NOT NULL,
  `code_applied` varchar(50) DEFAULT NULL,
  `amount_public` decimal(12,2) NOT NULL,
  `amount_supplier` decimal(12,2) NOT NULL DEFAULT '0.00',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rdisc_res_code` (`reservation_id`,`code_applied`),
  KEY `idx_rdisc_reservation` (`reservation_id`),
  KEY `idx_rdisc_discount` (`discount_id`),
  KEY `idx_rdisc_code` (`code_applied`),
  KEY `idx_rdisc_source` (`source`),
  CONSTRAINT `fk_rdisc_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`),
  CONSTRAINT `fk_reservation_discounts_discount` FOREIGN KEY (`discount_id`) REFERENCES `discounts` (`id`),
  CONSTRAINT `fk_reservation_discounts_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_drivers**

```
CREATE TABLE `reservation_drivers` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `app_customer_id` bigint unsigned DEFAULT NULL,
  `is_primary_driver` tinyint(1) NOT NULL DEFAULT '1',
  `first_name` varchar(150) NOT NULL,
  `last_name` varchar(150) NOT NULL,
  `email` varchar(255) DEFAULT NULL,
  `phone` varchar(50) DEFAULT NULL,
  `date_of_birth` date DEFAULT NULL,
  `driver_license_number` varchar(100) DEFAULT NULL,
  `driver_license_country` char(2) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rd_res_primary` (`reservation_id`,`is_primary_driver`),
  KEY `idx_rd_reservation` (`reservation_id`),
  KEY `idx_rd_customer` (`app_customer_id`),
  KEY `idx_rd_primary` (`reservation_id`,`is_primary_driver`),
  KEY `idx_rd_email` (`email`),
  KEY `idx_rd_phone` (`phone`),
  KEY `idx_rd_license` (`driver_license_number`,`driver_license_country`),
  CONSTRAINT `fk_rd_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`),
  CONSTRAINT `fk_reservation_drivers_customer` FOREIGN KEY (`app_customer_id`) REFERENCES `app_customers` (`id`),
  CONSTRAINT `fk_reservation_drivers_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_notes**

```
CREATE TABLE `reservation_notes` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `crm_user_id` bigint unsigned DEFAULT NULL,
  `source` enum('AGENT','SYSTEM','WHATSAPP','EMAIL','PHONE_CALL','OTHER') NOT NULL DEFAULT 'AGENT',
  `note_type` enum('INTERNAL','CUSTOMER_CONTACT','STATUS_CHANGE','PAYMENT','REFUND','REMINDER') NOT NULL DEFAULT 'INTERNAL',
  `title` varchar(255) DEFAULT NULL,
  `body` text NOT NULL,
  `metadata_json` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_res_notes_reservation_created` (`reservation_id`,`created_at`),
  KEY `idx_rn_reservation_created` (`reservation_id`,`created_at`),
  KEY `idx_rn_user_created` (`crm_user_id`,`created_at`),
  KEY `idx_rn_type_created` (`note_type`,`created_at`),
  KEY `idx_rn_source_created` (`source`,`created_at`),
  CONSTRAINT `fk_res_notes_crm_user` FOREIGN KEY (`crm_user_id`) REFERENCES `crm_users` (`id`),
  CONSTRAINT `fk_res_notes_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_pricing_items**

```
CREATE TABLE `reservation_pricing_items` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `item_type` enum('BASE_RATE','TAX','FEE','EXTRA','INSURANCE','DISCOUNT','OTHER') NOT NULL,
  `description` varchar(255) NOT NULL,
  `quantity` decimal(10,2) NOT NULL DEFAULT '1.00',
  `unit_price_public` decimal(12,2) NOT NULL DEFAULT '0.00',
  `unit_price_supplier` decimal(12,2) NOT NULL DEFAULT '0.00',
  `total_price_public` decimal(12,2) NOT NULL DEFAULT '0.00',
  `total_price_supplier` decimal(12,2) NOT NULL DEFAULT '0.00',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_rpi_reservation` (`reservation_id`),
  KEY `idx_rpi_type` (`reservation_id`,`item_type`),
  CONSTRAINT `fk_res_pricing_items_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`),
  CONSTRAINT `fk_rpi_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_status_history**

```
CREATE TABLE `reservation_status_history` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `old_status` enum('PENDING','ON_REQUEST','CONFIRMED','CANCELLED','NO_SHOW','IN_PROGRESS','COMPLETED') DEFAULT NULL,
  `new_status` enum('PENDING','ON_REQUEST','CONFIRMED','CANCELLED','NO_SHOW','IN_PROGRESS','COMPLETED') NOT NULL,
  `changed_by_crm_user_id` bigint unsigned DEFAULT NULL,
  `changed_by_system` varchar(100) DEFAULT NULL,
  `change_reason` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_res_status_history_crm_user` (`changed_by_crm_user_id`),
  KEY `fk_rsh_reservation` (`reservation_id`),
  CONSTRAINT `fk_res_status_history_crm_user` FOREIGN KEY (`changed_by_crm_user_id`) REFERENCES `crm_users` (`id`),
  CONSTRAINT `fk_res_status_history_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`),
  CONSTRAINT `fk_rsh_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_supplier_requests**

```
CREATE TABLE `reservation_supplier_requests` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `supplier_id` bigint unsigned NOT NULL,
  `request_type` varchar(32) NOT NULL,
  `idem_key` varchar(128) DEFAULT NULL,
  `attempt` int NOT NULL DEFAULT '0',
  `status` varchar(16) NOT NULL,
  `http_status` smallint DEFAULT NULL,
  `error_code` varchar(64) DEFAULT NULL,
  `error_message` varchar(255) DEFAULT NULL,
  `request_payload` json DEFAULT NULL,
  `response_payload` json DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  `created_date` date GENERATED ALWAYS AS (cast(`created_at` as date)) STORED,
  PRIMARY KEY (`id`),
  KEY `idx_reservation` (`reservation_id`),
  KEY `idx_supplier_status_created` (`supplier_id`,`status`,`created_at`),
  KEY `idx_type_status_created` (`request_type`,`status`,`created_at`),
  KEY `idx_rsr_supplier_status_created` (`supplier_id`,`status`,`created_at` DESC),
  KEY `idx_rsr_created_date` (`created_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_supplier_requests_new**

```
CREATE TABLE `reservation_supplier_requests_new` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `supplier_id` bigint unsigned NOT NULL,
  `request_type` varchar(32) NOT NULL,
  `idem_key` varchar(128) DEFAULT NULL,
  `attempt` int NOT NULL DEFAULT '0',
  `status` varchar(16) NOT NULL,
  `http_status` smallint DEFAULT NULL,
  `error_code` varchar(64) DEFAULT NULL,
  `error_message` varchar(255) DEFAULT NULL,
  `request_payload` json DEFAULT NULL,
  `response_payload` json DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  `created_date` date GENERATED ALWAYS AS (cast(`created_at` as date)) STORED,
  PRIMARY KEY (`id`),
  KEY `idx_reservation` (`reservation_id`),
  KEY `idx_supplier_status_created` (`supplier_id`,`status`,`created_at`),
  KEY `idx_type_status_created` (`request_type`,`status`,`created_at`),
  KEY `idx_rsr_supplier_status_created` (`supplier_id`,`status`,`created_at` DESC),
  KEY `idx_rsr_created_date` (`created_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_tag_pivot**

```
CREATE TABLE `reservation_tag_pivot` (
  `reservation_id` bigint unsigned NOT NULL,
  `tag_id` bigint unsigned NOT NULL,
  PRIMARY KEY (`reservation_id`,`tag_id`),
  KEY `idx_res_tag_pivot_tag` (`tag_id`),
  CONSTRAINT `fk_res_tag_pivot_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`),
  CONSTRAINT `fk_res_tag_pivot_tag` FOREIGN KEY (`tag_id`) REFERENCES `reservation_tags` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_tags**

```
CREATE TABLE `reservation_tag_pivot` (
  `reservation_id` bigint unsigned NOT NULL,
  `tag_id` bigint unsigned NOT NULL,
  PRIMARY KEY (`reservation_id`,`tag_id`),
  KEY `idx_res_tag_pivot_tag` (`tag_id`),
  CONSTRAINT `fk_res_tag_pivot_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`),
  CONSTRAINT `fk_res_tag_pivot_tag` FOREIGN KEY (`tag_id`) REFERENCES `reservation_tags` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservation_tasks**

```
CREATE TABLE `reservation_tasks` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint unsigned NOT NULL,
  `crm_user_id` bigint unsigned NOT NULL,
  `created_by_id` bigint unsigned DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `description` text,
  `due_at` datetime DEFAULT NULL,
  `status` enum('OPEN','IN_PROGRESS','DONE','CANCELLED') NOT NULL DEFAULT 'OPEN',
  `priority` enum('LOW','MEDIUM','HIGH','URGENT') NOT NULL DEFAULT 'MEDIUM',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_res_tasks_created_by` (`created_by_id`),
  KEY `idx_res_tasks_reservation_status` (`reservation_id`,`status`),
  KEY `idx_res_tasks_assignee_status` (`crm_user_id`,`status`),
  KEY `idx_rt_reservation` (`reservation_id`),
  KEY `idx_rt_user_status_due` (`crm_user_id`,`status`,`due_at`),
  KEY `idx_rt_status_due` (`status`,`due_at`),
  KEY `idx_rt_priority_status` (`priority`,`status`),
  CONSTRAINT `fk_res_tasks_created_by` FOREIGN KEY (`created_by_id`) REFERENCES `crm_users` (`id`),
  CONSTRAINT `fk_res_tasks_crm_user` FOREIGN KEY (`crm_user_id`) REFERENCES `crm_users` (`id`),
  CONSTRAINT `fk_res_tasks_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **reservations**

```
CREATE TABLE `reservations` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_code` varchar(50) NOT NULL,
  `app_customer_id` bigint unsigned DEFAULT NULL,
  `corporate_account_id` bigint unsigned DEFAULT NULL,
  `created_by_crm_user_id` bigint unsigned DEFAULT NULL,
  `supplier_id` bigint unsigned NOT NULL,
  `pickup_office_id` bigint unsigned NOT NULL,
  `dropoff_office_id` bigint unsigned NOT NULL,
  `car_category_id` bigint unsigned NOT NULL,
  `supplier_car_product_id` bigint unsigned DEFAULT NULL,
  `pickup_datetime` datetime NOT NULL,
  `dropoff_datetime` datetime NOT NULL,
  `rental_days` smallint unsigned NOT NULL,
  `currency_code` char(3) NOT NULL,
  `public_price_total` decimal(12,2) NOT NULL,
  `supplier_cost_total` decimal(12,2) NOT NULL,
  `discount_total` decimal(12,2) NOT NULL DEFAULT '0.00',
  `taxes_total` decimal(12,2) NOT NULL DEFAULT '0.00',
  `fees_total` decimal(12,2) NOT NULL DEFAULT '0.00',
  `commission_total` decimal(12,2) NOT NULL DEFAULT '0.00',
  `cashback_earned_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `status` enum('PENDING','ON_REQUEST','CONFIRMED','CANCELLED','NO_SHOW','IN_PROGRESS','COMPLETED') NOT NULL DEFAULT 'PENDING',
  `payment_status` enum('UNPAID','PAID','PARTIALLY_REFUNDED','REFUNDED','CHARGEBACK') NOT NULL DEFAULT 'UNPAID',
  `sales_channel_id` bigint unsigned NOT NULL,
  `traffic_source_id` bigint unsigned DEFAULT NULL,
  `marketing_campaign_id` bigint unsigned DEFAULT NULL,
  `affiliate_id` bigint unsigned DEFAULT NULL,
  `booking_device` enum('DESKTOP','MOBILE_WEB','IOS_APP','ANDROID_APP','CALL_CENTER') NOT NULL,
  `customer_ip` varchar(45) DEFAULT NULL,
  `customer_user_agent` varchar(500) DEFAULT NULL,
  `utm_source` varchar(150) DEFAULT NULL,
  `utm_medium` varchar(150) DEFAULT NULL,
  `utm_campaign` varchar(255) DEFAULT NULL,
  `utm_term` varchar(255) DEFAULT NULL,
  `utm_content` varchar(255) DEFAULT NULL,
  `supplier_name_snapshot` varchar(255) DEFAULT NULL,
  `pickup_office_code_snapshot` varchar(50) DEFAULT NULL,
  `pickup_office_name_snapshot` varchar(255) DEFAULT NULL,
  `dropoff_office_code_snapshot` varchar(50) DEFAULT NULL,
  `dropoff_office_name_snapshot` varchar(255) DEFAULT NULL,
  `pickup_city_name_snapshot` varchar(150) DEFAULT NULL,
  `pickup_country_name_snapshot` varchar(150) DEFAULT NULL,
  `car_acriss_code_snapshot` varchar(10) DEFAULT NULL,
  `car_category_name_snapshot` varchar(150) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `lock_version` int NOT NULL DEFAULT '0',
  `cancelled_at` datetime DEFAULT NULL,
  `cancel_reason` varchar(255) DEFAULT NULL,
  `supplier_reservation_code` varchar(64) DEFAULT NULL,
  `supplier_confirmed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_reservation_code` (`reservation_code`),
  KEY `fk_reservations_corporate` (`corporate_account_id`),
  KEY `fk_reservations_pickup_office` (`pickup_office_id`),
  KEY `fk_reservations_dropoff_office` (`dropoff_office_id`),
  KEY `fk_reservations_supplier_car_product` (`supplier_car_product_id`),
  KEY `idx_reservations_status` (`status`),
  KEY `idx_reservations_dates` (`pickup_datetime`,`dropoff_datetime`),
  KEY `idx_res_status_created` (`status`,`created_at`),
  KEY `idx_res_payment_status` (`payment_status`),
  KEY `idx_res_supplier_status` (`supplier_id`,`status`),
  KEY `idx_res_pickup_dt` (`pickup_datetime`),
  KEY `idx_res_customer` (`app_customer_id`),
  KEY `idx_res_created_by_created` (`created_by_crm_user_id`,`created_at`),
  KEY `idx_res_sales_channel_created` (`sales_channel_id`,`created_at`),
  KEY `idx_res_affiliate_created` (`affiliate_id`,`created_at`),
  KEY `idx_res_traffic_created` (`traffic_source_id`,`created_at`),
  KEY `idx_res_campaign_created` (`marketing_campaign_id`,`created_at`),
  KEY `idx_res_supplier_status_pickup` (`supplier_id`,`status`,`pickup_datetime`),
  KEY `idx_res_availability_check` (`car_category_id`,`supplier_id`,`pickup_datetime`,`dropoff_datetime`,`status`),
  CONSTRAINT `fk_reservations_affiliate` FOREIGN KEY (`affiliate_id`) REFERENCES `affiliates` (`id`),
  CONSTRAINT `fk_reservations_car_category` FOREIGN KEY (`car_category_id`) REFERENCES `car_categories` (`id`),
  CONSTRAINT `fk_reservations_corporate` FOREIGN KEY (`corporate_account_id`) REFERENCES `corporate_accounts` (`id`),
  CONSTRAINT `fk_reservations_crm_user` FOREIGN KEY (`created_by_crm_user_id`) REFERENCES `crm_users` (`id`),
  CONSTRAINT `fk_reservations_customer` FOREIGN KEY (`app_customer_id`) REFERENCES `app_customers` (`id`),
  CONSTRAINT `fk_reservations_dropoff_office` FOREIGN KEY (`dropoff_office_id`) REFERENCES `offices` (`id`),
  CONSTRAINT `fk_reservations_marketing_campaign` FOREIGN KEY (`marketing_campaign_id`) REFERENCES `marketing_campaigns` (`id`),
  CONSTRAINT `fk_reservations_pickup_office` FOREIGN KEY (`pickup_office_id`) REFERENCES `offices` (`id`),
  CONSTRAINT `fk_reservations_sales_channel` FOREIGN KEY (`sales_channel_id`) REFERENCES `sales_channels` (`id`),
  CONSTRAINT `fk_reservations_supplier` FOREIGN KEY (`supplier_id`) REFERENCES `suppliers` (`id`),
  CONSTRAINT `fk_reservations_supplier_car_product` FOREIGN KEY (`supplier_car_product_id`) REFERENCES `supplier_car_products` (`id`),
  CONSTRAINT `fk_reservations_traffic_source` FOREIGN KEY (`traffic_source_id`) REFERENCES `traffic_sources` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **sales_channels**

```
CREATE TABLE `sales_channels` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(50) NOT NULL,
  `name` varchar(150) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **supplier_brands**

```
CREATE TABLE `supplier_brands` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_supplier_brands_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
```



## **supplier_car_products**

```
CREATE TABLE `supplier_car_products` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `supplier_id` bigint unsigned NOT NULL,
  `car_category_id` bigint unsigned NOT NULL,
  `external_code` varchar(100) DEFAULT NULL,
  `name` varchar(255) NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scp_supplier_external` (`supplier_id`,`external_code`),
  KEY `fk_supplier_car_products_category` (`car_category_id`),
  KEY `idx_supplier_car_products_ext` (`supplier_id`,`external_code`),
  KEY `idx_scp_supplier_active` (`supplier_id`,`is_active`),
  KEY `idx_scp_supplier_category_active` (`supplier_id`,`car_category_id`,`is_active`),
  CONSTRAINT `fk_supplier_car_products_category` FOREIGN KEY (`car_category_id`) REFERENCES `car_categories` (`id`),
  CONSTRAINT `fk_supplier_car_products_supplier` FOREIGN KEY (`supplier_id`) REFERENCES `suppliers` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **suppliers**

```
CREATE TABLE `suppliers` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `legal_name` varchar(255) DEFAULT NULL,
  `website_url` varchar(255) DEFAULT NULL,
  `support_email` varchar(255) DEFAULT NULL,
  `support_phone` varchar(50) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `brand_id` bigint unsigned DEFAULT NULL,
  `country_code` char(2) DEFAULT NULL,
  `region_code` varchar(20) DEFAULT NULL,
  `external_supplier_code` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_suppliers_brand_country_name` (`brand_id`,`country_code`,`name`),
  KEY `idx_suppliers_brand` (`brand_id`),
  KEY `idx_suppliers_country` (`country_code`),
  CONSTRAINT `fk_suppliers_brand` FOREIGN KEY (`brand_id`) REFERENCES `supplier_brands` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **marketing_campaigns**

```
CREATE TABLE `marketing_campaigns` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `traffic_source_id` bigint unsigned DEFAULT NULL,
  `name` varchar(255) NOT NULL,
  `utm_source` varchar(150) DEFAULT NULL,
  `utm_medium` varchar(150) DEFAULT NULL,
  `utm_campaign` varchar(255) DEFAULT NULL,
  `utm_term` varchar(255) DEFAULT NULL,
  `utm_content` varchar(255) DEFAULT NULL,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_marketing_campaigns_source` (`traffic_source_id`),
  CONSTRAINT `fk_marketing_campaigns_source` FOREIGN KEY (`traffic_source_id`) REFERENCES `traffic_sources` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```



## **traffic_sources**

```
CREATE TABLE `traffic_sources` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(50) NOT NULL,
  `name` varchar(150) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

