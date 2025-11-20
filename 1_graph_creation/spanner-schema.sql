-- Spanner Schema for COBOL Modernization Knowledge Graph
-- This schema stores analyzed COBOL programs, business rules, and relationships based on code structure.

-- Programs table - stores COBOL program metadata
CREATE TABLE Programs (
  program_id STRING(36) NOT NULL,
  program_name STRING(100) NOT NULL,
  file_name STRING(200) NOT NULL,
  total_lines INT64,
  last_analyzed TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (program_id);

-- Business Entities table - stores identified business entities (variables, constants)
CREATE TABLE BusinessEntities (
  entity_id STRING(36) NOT NULL,
  entity_name STRING(200) NOT NULL,
  entity_type STRING(50) NOT NULL, -- e.g., 'variable', 'constant', 'copybook'
  description STRING(MAX),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (entity_id);

-- Program Relationships table - stores CALL relationships between programs
CREATE TABLE ProgramRelationships (
  relationship_id STRING(36) NOT NULL,
  source_program_id STRING(36) NOT NULL,
  target_program_id STRING(36) NOT NULL,
  relationship_type STRING(50) NOT NULL, -- e.g., 'CALLS'
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (source_program_id) REFERENCES Programs (program_id),
  FOREIGN KEY (target_program_id) REFERENCES Programs (program_id),
) PRIMARY KEY (relationship_id);

-- Code Sections table - stores analyzed code sections (Paragraphs, Sections)
CREATE TABLE CodeSections (
  section_id STRING(36) NOT NULL,
  program_id STRING(36) NOT NULL,
  section_name STRING(200) NOT NULL,
  section_type STRING(50) NOT NULL, -- e.g., 'DIVISION', 'SECTION', 'PARAGRAPH'
  start_line INT64,
  end_line INT64,
  content STRING(MAX),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (program_id) REFERENCES Programs (program_id),
) PRIMARY KEY (section_id);

-- Business Rules table - stores extracted business logic statements
CREATE TABLE BusinessRules (
  rule_id STRING(36) NOT NULL,
  section_id STRING(36) NOT NULL,
  rule_name STRING(200) NOT NULL,
  rule_type STRING(50), -- Nullable, for future classification
  technical_condition STRING(MAX), -- The actual IF/ELSE logic
  plain_english STRING(MAX), -- Explanation of the logic
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (section_id) REFERENCES CodeSections (section_id),
) PRIMARY KEY (rule_id);

-- Rule Entities table - mapping between rules and entities (Many-to-Many)
CREATE TABLE RuleEntities (
  rule_id STRING(36) NOT NULL,
  entity_id STRING(36) NOT NULL,
  usage_type STRING(50), -- 'reads', 'updates', 'validates'
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (rule_id) REFERENCES BusinessRules (rule_id),
  FOREIGN KEY (entity_id) REFERENCES BusinessEntities (entity_id),
) PRIMARY KEY (rule_id, entity_id);

-- Create indexes for common queries
CREATE INDEX ProgramsByName ON Programs(program_name);
CREATE INDEX RulesByType ON BusinessRules(rule_type);

-- Spanner Graph Definition
CREATE PROPERTY GRAPH CobolKnowledgeGraph
  NODE TABLES (
    Programs LABEL Program,
    BusinessEntities LABEL Entity,
    CodeSections LABEL Section,
    BusinessRules LABEL Rule
  )
  EDGE TABLES (
    ProgramRelationships
      SOURCE KEY (source_program_id) REFERENCES Programs (program_id)
      DESTINATION KEY (target_program_id) REFERENCES Programs (program_id)
      LABEL CALLS,
    CodeSections AS ContainsSection
      SOURCE KEY (program_id) REFERENCES Programs (program_id)
      DESTINATION KEY (section_id) REFERENCES CodeSections (section_id)
      LABEL CONTAINS,
    BusinessRules AS SectionContainsRule
      SOURCE KEY (section_id) REFERENCES CodeSections (section_id)
      DESTINATION KEY (rule_id) REFERENCES BusinessRules (rule_id)
      LABEL CONTAINS,
    RuleEntities
      SOURCE KEY (rule_id) REFERENCES BusinessRules (rule_id)
      DESTINATION KEY (entity_id) REFERENCES BusinessEntities (entity_id)
      LABEL USES
  );
