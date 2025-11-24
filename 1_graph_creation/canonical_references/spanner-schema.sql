-- Spanner Schema for COBOL Modernization Knowledge Graph (Line-Centric Model)
-- This schema stores analyzed COBOL programs at the line level for perfect fidelity and traceability.

-- 1. Programs table (Metadata)
CREATE TABLE Programs (
  program_id STRING(256) NOT NULL,
  program_name STRING(100) NOT NULL,
  file_name STRING(200) NOT NULL,
  total_lines INT64,
  last_analyzed TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (program_id);

-- 2. Source Code Lines (The Atomic Unit)
-- Every single line of code is a record.
CREATE TABLE SourceCodeLines (
  line_id STRING(256) NOT NULL, -- Format: {program_id}_{line_number}
  program_id STRING(256) NOT NULL,
  line_number INT64 NOT NULL,
  content STRING(MAX) NOT NULL, -- Raw text
  type STRING(50) NOT NULL, -- 'CODE', 'COMMENT', 'BLANK', 'DIRECTIVE'
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (program_id) REFERENCES Programs (program_id),
) PRIMARY KEY (line_id);

-- 3. Code Structure (The Hierarchy)
-- Divisions, Sections, Paragraphs.
CREATE TABLE CodeStructure (
  structure_id STRING(256) NOT NULL,
  program_id STRING(256) NOT NULL,
  parent_structure_id STRING(256), -- Recursive relationship (e.g. Section -> Division)
  name STRING(200) NOT NULL,
  type STRING(50) NOT NULL, -- 'DIVISION', 'SECTION', 'PARAGRAPH'
  start_line_number INT64 NOT NULL,
  end_line_number INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (program_id) REFERENCES Programs (program_id),
  FOREIGN KEY (parent_structure_id) REFERENCES CodeStructure (structure_id),
) PRIMARY KEY (structure_id);

-- 4. Data Entities (Variables, Files)
CREATE TABLE DataEntities (
  entity_id STRING(256) NOT NULL,
  program_id STRING(256) NOT NULL,
  name STRING(200) NOT NULL,
  type STRING(50) NOT NULL, -- 'VARIABLE', 'FILE', 'COPYBOOK'
  definition_line_id STRING(256), -- Where it is defined
  description STRING(MAX),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (program_id) REFERENCES Programs (program_id),
  FOREIGN KEY (definition_line_id) REFERENCES SourceCodeLines (line_id),
) PRIMARY KEY (entity_id);

-- 5. Line References (The Usage Edges)
-- Links lines to the entities they use.
CREATE TABLE LineReferences (
  reference_id STRING(256) NOT NULL,
  source_line_id STRING(256) NOT NULL,
  target_entity_id STRING(256) NOT NULL,
  usage_type STRING(50) NOT NULL, -- 'READS', 'WRITES', 'DECLARATION'
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (source_line_id) REFERENCES SourceCodeLines (line_id),
  FOREIGN KEY (target_entity_id) REFERENCES DataEntities (entity_id),
) PRIMARY KEY (reference_id);

-- 6. Control Flow (The Execution Edges)
-- Links lines (PERFORM/GO TO) to target Structures (Paragraphs).
CREATE TABLE ControlFlow (
  flow_id STRING(256) NOT NULL,
  source_line_id STRING(256) NOT NULL,
  target_structure_id STRING(256) NOT NULL,
  type STRING(50) NOT NULL, -- 'PERFORM', 'GO_TO', 'CALL'
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FOREIGN KEY (source_line_id) REFERENCES SourceCodeLines (line_id),
  FOREIGN KEY (target_structure_id) REFERENCES CodeStructure (structure_id),
) PRIMARY KEY (flow_id);

-- Spanner Graph Definition
CREATE PROPERTY GRAPH CobolLineGraph
  NODE TABLES (
    Programs LABEL Program,
    SourceCodeLines LABEL Line,
    CodeStructure LABEL Structure,
    DataEntities LABEL Entity
  )
  EDGE TABLES (
    -- Hierarchy: Structure contains Lines
    SourceCodeLines AS ContainsLine
      SOURCE KEY (program_id) REFERENCES Programs (program_id) -- Simplification, could traverse Structure
      DESTINATION KEY (line_id) REFERENCES SourceCodeLines (line_id)
      LABEL HAS_LINE,
    
    -- Hierarchy: Structure Parent/Child
    CodeStructure AS ParentStructure
      SOURCE KEY (parent_structure_id) REFERENCES CodeStructure (structure_id)
      DESTINATION KEY (structure_id) REFERENCES CodeStructure (structure_id)
      LABEL CONTAINS_CHILD,

    -- Usage: Line uses Entity
    LineReferences
      SOURCE KEY (source_line_id) REFERENCES SourceCodeLines (line_id)
      DESTINATION KEY (target_entity_id) REFERENCES DataEntities (entity_id)
      LABEL REFERENCES,

    -- Flow: Line calls Structure
    ControlFlow
      SOURCE KEY (source_line_id) REFERENCES SourceCodeLines (line_id)
      DESTINATION KEY (target_structure_id) REFERENCES CodeStructure (structure_id)
      LABEL CALLS
  );
