// Equipment-name validation shared by transport and presentation. No game reads.
#include "coop_equipment.h"
#include <string.h>

int coop_equipment_valid(const CoopEquipment *equipment) {
    if (!equipment) return 0;
    for (int slot=0;slot<COOP_EQUIP_SLOTS;slot++) {
        const char *name=equipment->actor[slot];
        const char *end=memchr(name,0,COOP_EQUIP_NAME);
        if (!end) return 0;
        for (const char *p=end;p<name+COOP_EQUIP_NAME;p++) if (*p) return 0;
        if (!name[0]) continue;
        const char *number=NULL;
        if (slot==COOP_EQUIP_WEAPON) {
            const char *const prefixes[]={"Weapon_Sword_","Weapon_Lsword_","Weapon_Spear_"};
            for (unsigned i=0;i<3;i++) if (!strncmp(name,prefixes[i],strlen(prefixes[i])))
                number=name+strlen(prefixes[i]);
        } else {
            const char *prefix=slot==COOP_EQUIP_SHIELD ? "Weapon_Shield_" : "Weapon_Bow_";
            if (!strncmp(name,prefix,strlen(prefix))) number=name+strlen(prefix);
        }
        if (!number || number[0]<'0' || number[0]>'9') return 0;
        for (const char *p=number;p<end;p++)
            if (!((*p>='0' && *p<='9') || (*p>='A' && *p<='Z') ||
                  (*p>='a' && *p<='z') || *p=='_')) return 0;
    }
    return 1;
}
