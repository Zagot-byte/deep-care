-- setup_postgres.sql — Deep Care mock data (10 customers)
-- Run: sudo -u postgres psql -f setup_postgres.sql

CREATE DATABASE deepcare;
\c deepcare;

CREATE TABLE IF NOT EXISTS customers (
    dob         VARCHAR(12)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    customer_id VARCHAR(20)  NOT NULL,
    data        JSONB        NOT NULL DEFAULT '{}'
);

INSERT INTO customers (dob, name, customer_id, data) VALUES ('15-03-1999','Arjun Kumar','DCID-4521','{"orders":[{"order_id":"ORD-4521","item":"Laptop Stand","status":"Delivered","tracking":"TRK-001"},{"order_id":"ORD-4522","item":"Wireless Mouse","status":"Out for Delivery","tracking":"TRK-002"}],"bills":[{"month":"March 2024","amount":2400,"due_date":"2024-03-20","status":"unpaid","history":[{"month":"Feb 2024","amount":2200,"status":"paid"}]}],"complaints":[{"complaint_id":"CMP-001","issue":"Billing overcharge","status":"open","escalated":false}],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

INSERT INTO customers (dob, name, customer_id, data) VALUES ('20-05-1995','Priya Sharma','DCID-7891','{"orders":[{"order_id":"ORD-7891","item":"Bluetooth Speaker","status":"Processing","tracking":"TRK-003"}],"bills":[{"month":"March 2024","amount":1800,"due_date":"2024-03-25","status":"autopay","history":[]}],"complaints":[],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

INSERT INTO customers (dob, name, customer_id, data) VALUES ('08-11-1988','Ravi Shankar','DCID-3301','{"orders":[{"order_id":"ORD-3301","item":"Smart Watch","status":"Delivered","tracking":"TRK-010"},{"order_id":"ORD-3302","item":"Charging Dock","status":"Delivered","tracking":"TRK-011"}],"bills":[{"month":"March 2024","amount":3200,"due_date":"2024-03-18","status":"paid","history":[{"month":"Feb 2024","amount":2900,"status":"paid"}]}],"complaints":[{"complaint_id":"CMP-010","issue":"Watch not syncing with phone","status":"resolved","escalated":false}],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

INSERT INTO customers (dob, name, customer_id, data) VALUES ('14-07-1992','Meena Pillai','DCID-5512','{"orders":[{"order_id":"ORD-5512","item":"Air Purifier","status":"Out for Delivery","tracking":"TRK-020"}],"bills":[{"month":"March 2024","amount":5500,"due_date":"2024-03-22","status":"unpaid","history":[{"month":"Feb 2024","amount":5500,"status":"paid"}]}],"complaints":[{"complaint_id":"CMP-020","issue":"Previous air purifier delivered damaged","status":"escalated","escalated":true},{"complaint_id":"CMP-021","issue":"Refund not processed after 10 days","status":"open","escalated":false}],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

INSERT INTO customers (dob, name, customer_id, data) VALUES ('03-02-1990','Karthik Nair','DCID-6623','{"orders":[{"order_id":"ORD-6623","item":"Gaming Headset","status":"Delivered","tracking":"TRK-030"},{"order_id":"ORD-6624","item":"Mechanical Keyboard","status":"Processing","tracking":"TRK-031"},{"order_id":"ORD-6625","item":"Monitor Stand","status":"Shipped","tracking":"TRK-032"}],"bills":[{"month":"March 2024","amount":7800,"due_date":"2024-03-28","status":"unpaid","history":[{"month":"Feb 2024","amount":6200,"status":"paid"}]}],"complaints":[],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

INSERT INTO customers (dob, name, customer_id, data) VALUES ('25-09-1997','Ananya Bose','DCID-8834','{"orders":[{"order_id":"ORD-8834","item":"Yoga Mat Premium","status":"Delivered","tracking":"TRK-040"},{"order_id":"ORD-8835","item":"Resistance Bands Set","status":"Delivered","tracking":"TRK-041"}],"bills":[{"month":"March 2024","amount":1200,"due_date":"2024-03-30","status":"autopay","history":[{"month":"Feb 2024","amount":1200,"status":"paid"}]}],"complaints":[{"complaint_id":"CMP-030","issue":"Yoga mat colour different from website","status":"resolved","escalated":false}],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

INSERT INTO customers (dob, name, customer_id, data) VALUES ('17-12-1975','Suresh Iyer','DCID-2210','{"orders":[{"order_id":"ORD-2210","item":"Coffee Maker Deluxe","status":"Delivered","tracking":"TRK-050"}],"bills":[{"month":"March 2024","amount":4600,"due_date":"2024-03-15","status":"overdue","history":[{"month":"Feb 2024","amount":4600,"status":"paid"}]}],"complaints":[{"complaint_id":"CMP-040","issue":"Coffee maker stopped working after 2 weeks","status":"open","escalated":false}],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

INSERT INTO customers (dob, name, customer_id, data) VALUES ('30-04-1993','Divya Menon','DCID-9945','{"orders":[{"order_id":"ORD-9945","item":"Skincare Gift Set","status":"Delivered","tracking":"TRK-060"},{"order_id":"ORD-9946","item":"Vitamin Supplements 3-Month Pack","status":"Shipped","tracking":"TRK-061"}],"bills":[{"month":"March 2024","amount":2100,"due_date":"2024-03-27","status":"unpaid","history":[{"month":"Feb 2024","amount":1900,"status":"paid"}]}],"complaints":[],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

INSERT INTO customers (dob, name, customer_id, data) VALUES ('11-08-1985','Vikram Desai','DCID-1156','{"orders":[{"order_id":"ORD-1156","item":"4K Action Camera","status":"Delivered","tracking":"TRK-070"},{"order_id":"ORD-1157","item":"Waterproof Camera Case","status":"Delivered","tracking":"TRK-071"},{"order_id":"ORD-1158","item":"Extra Battery Pack","status":"Out for Delivery","tracking":"TRK-072"}],"bills":[{"month":"March 2024","amount":12500,"due_date":"2024-03-20","status":"paid","history":[{"month":"Feb 2024","amount":8900,"status":"paid"}]}],"complaints":[{"complaint_id":"CMP-050","issue":"Camera firmware update bricked device","status":"escalated","escalated":true}],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

INSERT INTO customers (dob, name, customer_id, data) VALUES ('22-01-1980','Lakshmi Krishnan','DCID-3378','{"orders":[{"order_id":"ORD-3378","item":"Stand Mixer Professional","status":"Processing","tracking":"TRK-080"}],"bills":[{"month":"March 2024","amount":9200,"due_date":"2024-03-31","status":"unpaid","history":[{"month":"Feb 2024","amount":9200,"status":"paid"}]}],"complaints":[{"complaint_id":"CMP-060","issue":"Wrong model delivered","status":"open","escalated":false},{"complaint_id":"CMP-061","issue":"Return pickup not scheduled despite 3 requests","status":"escalated","escalated":true}],"session_history":[]}') ON CONFLICT (dob) DO NOTHING;

SELECT dob, name, customer_id,
  jsonb_array_length(data->'orders')     AS orders,
  jsonb_array_length(data->'complaints') AS complaints
FROM customers ORDER BY customer_id;
