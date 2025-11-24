-- Incremental Schema Update
-- Run this to add Execution Flow support to an existing database.

-- 1. Add RuleEntities table if missing
CREATE TABLE RuleEntities (
  rule_id STRING(256) NOT NULL,
  entity_id STRING(256) NOT NULL,
  usage_type STRING(50),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (rule_id) REFERENCES BusinessRules (rule_id),
  FOREIGN KEY (entity_id) REFERENCES BusinessEntities (entity_id),
) PRIMARY KEY (rule_id, entity_id);

-- 2. Add SectionCalls table if missing
CREATE TABLE SectionCalls (
  call_id STRING(256) NOT NULL,
  source_section_id STRING(256) NOT NULL,
  target_section_id STRING(256) NOT NULL,
  call_type STRING(50) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (source_section_id) REFERENCES CodeSections (section_id),
  FOREIGN KEY (target_section_id) REFERENCES CodeSections (section_id),
) PRIMARY KEY (call_id);

-- 3. Update Graph Definition (Replaces existing graph)
CREATE OR REPLACE PROPERTY GRAPH CobolKnowledgeGraph
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
      LABEL HAS_SECTION,
    BusinessRules AS SectionContainsRule
      SOURCE KEY (section_id) REFERENCES CodeSections (section_id)
      DESTINATION KEY (rule_id) REFERENCES BusinessRules (rule_id)
      LABEL HAS_RULE,
    RuleEntities
      SOURCE KEY (rule_id) REFERENCES BusinessRules (rule_id)
      DESTINATION KEY (entity_id) REFERENCES BusinessEntities (entity_id)
      LABEL REFERENCES_ENTITY,
    SectionCalls
      SOURCE KEY (source_section_id) REFERENCES CodeSections (section_id)
      DESTINATION KEY (target_section_id) REFERENCES CodeSections (section_id)
      LABEL SECTION_CALLS
  );
