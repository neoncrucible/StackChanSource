#pragma once
namespace {
bool device_ack(const char* id, const char* name, cJSON* payload, char* output, size_t capacity) {
    cJSON* root=cJSON_CreateObject();
    if (!root || !payload) { cJSON_Delete(root); cJSON_Delete(payload); return false; }
    cJSON_AddNumberToObject(root,"v",1);
    cJSON_AddStringToObject(root,"id",id);
    cJSON_AddStringToObject(root,"ts","device");
    cJSON_AddStringToObject(root,"kind","ack");
    cJSON_AddStringToObject(root,"name",name);
    cJSON_AddItemToObject(root,"payload",payload);
    const bool ok=cJSON_PrintPreallocated(root,output,static_cast<int>(capacity),false);
    cJSON_Delete(root);
    return ok;
}
}
