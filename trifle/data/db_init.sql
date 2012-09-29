CREATE TABLE items (id INTEGER PRIMARY KEY,
                    title TEXT,
                    author VARCHAR(1024),
                    summary VARCHAR(141),
                    href VARCHAR(1024),
                    time UNSIGNED BIG INT DEFAULT 0,
                    update_time UNSIGNED BIG INT DEFAULT 0,
                    subscription VARCHAR(1024),
                    unread BOOLEAN DEFAULT 0,
                    starred BOOLEAN DEFAULT 0,
                    to_sync BOOLEAN DEFAULT 0,
                    to_delete BOOLEAN DEFAULT 0);

CREATE TABLE subscriptions (id VARCHAR(1024),
                            url VARCHAR(1024),
                            title VARCHAR(1024));

CREATE TABLE labels (id INTEGER,
                     name VARCHAR(1024),
                     subscriptions VARCHAR(1024));

CREATE TABLE flags (item_id INTEGER,
                    flag VARCHAR(1024));
