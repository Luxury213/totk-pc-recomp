// Equipment identity is presentation data, never an inventory transaction.
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { COOP_EQUIP_WEAPON, COOP_EQUIP_SHIELD, COOP_EQUIP_BOW, COOP_EQUIP_SLOTS,
       COOP_EQUIP_NAME = 48, COOP_EQUIP_BYTES = COOP_EQUIP_SLOTS * COOP_EQUIP_NAME };
typedef struct { char actor[COOP_EQUIP_SLOTS][COOP_EQUIP_NAME]; } CoopEquipment;
int coop_equipment_valid(const CoopEquipment *equipment);
// Guest observer only, 1.4.3. A failed/unstable read leaves out unchanged.
int coop_equipment_observe(CoopEquipment *out);
#ifdef __cplusplus
}
#endif
