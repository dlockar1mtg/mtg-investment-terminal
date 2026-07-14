from dataclasses import dataclass
from terminal2.warehouse_core import DatasetDefinition
@dataclass(frozen=True)
class ExpansionContract:
 name:str;description:str;primary_key:tuple[str,...];required_columns:tuple[str,...];snapshot:bool=True
 def definition(self):
  return DatasetDefinition(name=self.name,category='secret_lair',module='terminal2.secret_lair.intelligence_expansion',description=self.description,primary_key=self.primary_key,expected_columns=self.required_columns,required=True,snapshot=self.snapshot,version='1')
BASE=('investment_product_id','asset_class','product_name')
EXPANSION_CONTRACTS={
'secret_lair_investment_universe':ExpansionContract('secret_lair_investment_universe','Canonical investable Secret Lair universe.',('investment_product_id',),BASE+('secret_lair_id','product_type','current_price','msrp_usd')),
'secret_lair_feature_matrix':ExpansionContract('secret_lair_feature_matrix','Secret Lair-specific engineered features.',('investment_product_id',),BASE+('product_age_months','premium_to_msrp','observation_count','metadata_completeness')),
'secret_lair_risk_assessment':ExpansionContract('secret_lair_risk_assessment','Dedicated Secret Lair risk decomposition.',('investment_product_id',),BASE+('overall_risk_score','risk_rating','volatility_risk','liquidity_risk','drawdown_risk','data_risk')),
'secret_lair_confidence_assessment':ExpansionContract('secret_lair_confidence_assessment','Secret Lair evidence confidence.',('investment_product_id',),BASE+('overall_confidence_score','confidence_rating','price_history_score','metadata_score','coverage_score')),
'secret_lair_investment_scores':ExpansionContract('secret_lair_investment_scores','Dedicated Secret Lair factor score.',('investment_product_id',),BASE+('investment_score','risk_adjusted_score','momentum_score','scarcity_score','ip_artist_score')),
'secret_lair_recommendations':ExpansionContract('secret_lair_recommendations','Secret Lair recommendations.',('investment_product_id',),BASE+('recommendation','recommendation_score','overall_confidence_score','overall_risk_score')),
'secret_lair_recommendation_factors':ExpansionContract('secret_lair_recommendation_factors','Long-form Secret Lair factors.',('investment_product_id','factor_code'),BASE+('factor_code','factor_group','factor_value','factor_score','factor_direction'),False),
'secret_lair_executive_buy_list':ExpansionContract('secret_lair_executive_buy_list','Ranked Secret Lair opportunities.',('investment_product_id',),BASE+('buy_list_rank','recommendation','recommendation_score')),
'secret_lair_model_coverage':ExpansionContract('secret_lair_model_coverage','Secret Lair data and model coverage.',('investment_product_id',),BASE+('registry_available','pricing_available','history_available','available_component_count','model_coverage_score')),
'secret_lair_intelligence_summary':ExpansionContract('secret_lair_intelligence_summary','Executive Secret Lair intelligence summary.',('snapshot_date',),('snapshot_date','asset_count','priced_asset_count','actionable_count','average_score','average_confidence','average_risk')),
'unified_investment_products':ExpansionContract('unified_investment_products','Unified booster and Secret Lair product dimension.',('investment_product_id',),BASE+('product_type','current_price')),
'unified_investment_recommendations':ExpansionContract('unified_investment_recommendations','Unified cross-asset recommendations.',('investment_product_id',),BASE+('recommendation','recommendation_score','overall_confidence_score','overall_risk_score')),
'unified_executive_buy_list':ExpansionContract('unified_executive_buy_list','Unified ranked opportunity list.',('investment_product_id',),BASE+('unified_rank','recommendation','recommendation_score')),
'unified_asset_class_summary':ExpansionContract('unified_asset_class_summary','Comparison summary by asset class.',('asset_class',),('asset_class','product_count','priced_product_count','actionable_count','average_recommendation_score','average_confidence','average_risk'))}
def get_expansion_contract(name):
 try:return EXPANSION_CONTRACTS[name]
 except KeyError as exc:raise KeyError(f'Unknown expansion contract: {name}') from exc
