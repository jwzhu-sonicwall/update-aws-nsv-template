import os
import botocore.session
import json

REGION_LIST = [
    "us-east-1"
]

Filters=[
    {
        'Name': 'name',
        'Values': [
            'SonicWall*',
        ]
    },
    {
        'Name': 'product-code.type',
        'Values': [
            'marketplace',
        ]
    },
]

class GenerateFile:
    def __init__(self) -> None:
        self.session = botocore.session.get_session()
        self.mappings = {}
        self.mappings_to_json = ""
        self.CF_NEW_VPC_TEMPLATE = ""
        self.CF_EXISTING_VPC_TEMPLATE = ""

    def generate_mapping(self):
        for region in REGION_LIST:
            client = self.session.create_client("ec2", region_name=region)
            response = client.describe_images(Filters=Filters)
            self.mappings[region] = list()
            for i in range(len(response["Images"])):
                img = response["Images"][i]
                if "DeprecationTime" not in img:
                    continue
                self.mappings[region].append({
                    "Description" : img["Description"].replace('_', ''),
                    "ImageId" : img["ImageId"],
                })
            self.mappings[region].sort(key=lambda d : d["Description"])
        # for test single version
        # self.mappings['us-east-2'].append({
        #     "Description" : "SonicWallNSvR9999",
        #     "ImageId" : "ami-9999",
        # })

    def generate_mapping_from_json(self, file) -> dict:
        res_mapping = {}
        f_content = ""
        with open(os.path.join('./sonicwall-nsv-aws-cf-templates', file), 'r') as f:
            f_content = f.read()
        # print(f_content)
        json_f = json.loads(f_content)
        if "Mappings" not in json_f:
            return res_mapping
        for region_name, region in json_f["Mappings"]["RegionMap"].items():
            res_mapping[region_name] = list()
            for imgD, imgId in region.items():
                # print(imgD, imgId)
                res_mapping[region_name].append({
                    "Description" : imgD,
                    "ImageId" : imgId,
                })
        return res_mapping
    
    def cmp_over_version(self, old_version, new_version, is_new) -> str:
        ret = f"{'Add New' if is_new else 'Delete Old'} version:\n"
        new_regions = []
        new_imgs = []
        for region_name, region in new_version.items():
            if region_name not in old_version:
                new_regions.append((region_name, region))
            else:
                for new_img in region:
                    flag = True
                    for old_img in old_version[region_name]:
                        if new_img['Description'] == old_img['Description']:
                            if new_img['ImageId'] != old_img['ImageId']:
                                new_imgs.append((region_name, new_img['Description'], new_img['ImageId']))
                            flag = False
                            break
                    if flag is True:
                        new_imgs.append((region_name, new_img['Description'], new_img['ImageId']))
        if len(new_regions) == 0 and len(new_imgs) == 0:
            ret += f"\tNo {'new' if is_new else 'old'} versions\n"
        else:
            if len(new_regions) != 0:
                for region_name, region in new_regions:
                    for img in region:
                        ret += f"\tregion:{region_name}, Description:{img['Description']}, ImageId:{img['ImageId']}\n"
            if len(new_imgs) != 0:
                for region_name, imgD, imgId in new_imgs:
                    ret += f"\tregion:{region_name}, Description:{imgD}, ImageId:{imgId}\n"
        return ret

    def cmp_versions(self, old_version : dict) -> str:
        new_version = self.mappings
        ret = self.cmp_over_version(old_version, new_version, True)
        ret += self.cmp_over_version(new_version, old_version, False)
        return ret

    def transfer_mapping_to_json(self):
        cnt = 0
        self.mappings_to_json += '    "Mappings" : {\n        "RegionMap" : {\n'
        for region, li in self.mappings.items():
            self.mappings_to_json += f'{" " * 12}"{region}" : {{\n'
            for i in range(len(li)):
                dic = li[i]
                if i == len(li) - 1:
                    self.mappings_to_json += f'{" " * 16}"{dic["Description"]}" : "{dic["ImageId"]}"\n'
                else:
                    self.mappings_to_json += f'{" " * 16}"{dic["Description"]}" : "{dic["ImageId"]}",\n'
            if cnt == len(self.mappings) - 1:
                self.mappings_to_json += f'{" " * 12}}}\n'
            else:
                self.mappings_to_json += f'{" " * 12}}},\n'
            cnt += 1
        self.mappings_to_json += '        }\n    },\n'

    def find_mappings_pos(self, lis) -> tuple:
        st, en = -1, -1
        for i, li in enumerate(lis):
            if 'Description' in li:
                st = i
            elif st != -1 and 'Metadata' in li:
                en = i
                break
        return st, en
    
    def find_amiId_pos(self, lis) -> tuple:
        st, en = -1, -1
        for i, li in enumerate(lis):
            if i > 0 and 'AmiId' in lis[i - 1] and 'Description' in li:
                st = i
            elif st != -1 and 'AvailabilityZone' in li:
                en = i - 1
                break
        return st, en
    
    def find_imageId_pos(self, lis) -> int:
        pos = -1
        for i, li in enumerate(lis):
            if i > 0 and 'ImageId' in lis[i - 1]:
                pos = i
                break
        return pos

    def template_file_update(self, file) -> str:
        content = None
        with open(os.path.join('./sonicwall-nsv-aws-cf-templates', file), 'r') as f:
            content = f.readlines()
        
        if content is None:
            print(f'open file {file} failed!')
            return None
        mappings_st, mappings_en = self.find_mappings_pos(content)
        if mappings_st == -1 or mappings_en == -1:
            return None
        content = content[:mappings_st + 1] + [self.mappings_to_json] + content[mappings_en:]

        amiId_st, amiId_en = self.find_amiId_pos(content)
        if amiId_st == -1 or amiId_en == -1:
            return None
        content = content[:amiId_st + 1] + [f'            "AllowedValues": {json.dumps([dic["Description"].replace("_", "") for dic in max(list(self.mappings.values()), key=lambda x : len(x))])},\n', '            "Type": "String"\n'] + content[amiId_en:]

        imageId_pos = self.find_imageId_pos(content)
        if imageId_pos == -1:
            return None
        content = content[:imageId_pos] + ['                    "Fn::FindInMap" : [ "RegionMap", { "Ref" : "AWS::Region" }, {"Ref" : "AmiId"}]\n'] + content[imageId_pos + 1:]
        return ''.join(content)

    def generate_files(self):
        self.generate_mapping()
        self.transfer_mapping_to_json()
        self.CF_NEW_VPC_TEMPLATE = self.template_file_update('single-ami/cf-new-vpc.template')
        self.CF_EXISTING_VPC_TEMPLATE = self.template_file_update('single-ami/cf-existing-vpc.template')

if __name__ == '__main__':
    from aws_template_git import HandleGit
    native_path = './sonicwall-nsv-aws-cf-templates'
    generateFile = GenerateFile()
    generateFile.generate_files()
    handleGit = HandleGit()
    handleGit.rewrite_file(os.path.join(native_path, "single-ami/cf-existing-vpc.template"), generateFile.CF_EXISTING_VPC_TEMPLATE)
    handleGit.rewrite_file(os.path.join(native_path, "single-ami/cf-new-vpc.template"), generateFile.CF_NEW_VPC_TEMPLATE)
    # print(generateFile.CF_NEW_VPC_TEMPLATE)
    # print(generateFile.CF_EXISTING_VPC_TEMPLATE)
