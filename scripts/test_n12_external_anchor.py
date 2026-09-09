from quantbot.research.artifact_store import seal
from quantbot.research.non_oos_series import validate_external_n12_anchor

def blocked(fn):
 try:fn()
 except Exception:return
 raise AssertionError('anchor_bypass')
def main():
 n11='a'*64; sha='b'*64
 rows=[]
 for i in range(2):
  ch=str(i+1)*64;rows.append({'candidate':{'candidate_identity':ch,'validation_result_identity':str(i+3)*64,'selected_train_result_identity':'5'*64,'task_identity':'6'*64,'model_id':f'm{i}','family':'f','symbol':f'S{i}','params':{}},'series_file':'x'})
 manifest=seal({'schema_version':'quantbot-non-oos-series-manifest-n12-v1','input_n11_artifact_identity':n11,'candidate_count':2,'series_count':4,'rows':rows,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
 diagnostic=seal({'schema_version':'quantbot-non-oos-homogeneity-n12-v1','input_n11_artifact_identity':n11,'candidate_count':2,'correlation_file_sha256':sha,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED','selection_rule_changed':False})
 assert validate_external_n12_anchor(diagnostic,manifest,expected_n11_identity=n11,expected_candidate_count=2,actual_correlation_sha256=sha)
 bad=seal({**{k:v for k,v in manifest.items() if k!='artifact_identity'},'series_count':3});blocked(lambda:validate_external_n12_anchor(diagnostic,bad,expected_n11_identity=n11,expected_candidate_count=2,actual_correlation_sha256=sha))
 badrows=[dict(row) for row in rows];badrows[1]['candidate']=dict(badrows[1]['candidate']);badrows[1]['candidate']['validation_result_identity']=badrows[0]['candidate']['validation_result_identity'];bad=seal({**{k:v for k,v in manifest.items() if k!='artifact_identity'},'rows':badrows});blocked(lambda:validate_external_n12_anchor(diagnostic,bad,expected_n11_identity=n11,expected_candidate_count=2,actual_correlation_sha256=sha))
 blocked(lambda:validate_external_n12_anchor(diagnostic,manifest,expected_n11_identity=n11,expected_candidate_count=2,actual_correlation_sha256='c'*64))
 badschema=seal({**{k:v for k,v in manifest.items() if k!='artifact_identity'},'schema_version':'quantbot-non-oos-series-n12-v1'});blocked(lambda:validate_external_n12_anchor(diagnostic,badschema,expected_n11_identity=n11,expected_candidate_count=2,actual_correlation_sha256=sha))

 print('N12_EXTERNAL_ANCHOR_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
