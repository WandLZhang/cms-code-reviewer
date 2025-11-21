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
      LABEL HAS_SECTION,
    BusinessRules AS SectionContainsRule
      SOURCE KEY (section_id) REFERENCES CodeSections (section_id)
      DESTINATION KEY (rule_id) REFERENCES BusinessRules (rule_id)
      LABEL HAS_RULE,
    RuleEntities
      SOURCE KEY (rule_id) REFERENCES BusinessRules (rule_id)
      DESTINATION KEY (entity_id) REFERENCES BusinessEntities (entity_id)
      LABEL REFERENCES_ENTITY
  );
