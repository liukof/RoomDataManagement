-- Tabella Catalogo Oggetti
CREATE TABLE items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    item_code TEXT NOT NULL,
    item_description TEXT,
    UNIQUE(project_id, item_code)
);

-- Tabella di collegamento Stanza-Oggetti
CREATE TABLE room_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id UUID REFERENCES rooms(id) ON DELETE CASCADE,
    item_id UUID REFERENCES items(id) ON DELETE CASCADE,
    quantity INTEGER DEFAULT 1
);
